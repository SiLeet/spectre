//! Per-client, in-memory rate limiting for the memory endpoints.
//!
//! `/api/read` and `/api/search` touch target-process memory, so each client
//! IP may only issue [`RateLimit::max_requests`] of them per
//! [`RateLimit::window`] (default: [`DEFAULT_RATE_LIMIT`] per minute). Both
//! endpoints share one budget per client. Requests over the limit get a JSON
//! 429 with a `Retry-After` header.
//!
//! The limiter uses fixed windows: a client's window starts with its first
//! request and its counter resets once the window has elapsed. Time comes from
//! an injectable [`Clock`], so tests can step through windows without
//! sleeping ([`ManualClock`]).
//!
//! Memory is bounded: at most [`MAX_TRACKED_CLIENTS`] clients are tracked.
//! When the table is full, expired windows are evicted first, then the
//! client with the oldest window.

use std::collections::HashMap;
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::{Duration, Instant};

use anyhow::{Result, bail};
use axum::extract::{ConnectInfo, Request, State};
use axum::http::{HeaderValue, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use tracing::{debug, warn};

use crate::error::ApiError;

/// Default number of `/api/read` + `/api/search` requests per client and minute.
pub const DEFAULT_RATE_LIMIT: u32 = 60;
/// Most clients the limiter keeps state for (bounds its memory use).
pub const MAX_TRACKED_CLIENTS: usize = 1024;

// ── Clock ────────────────────────────────────────────────────────────────────

/// Source of the current time for the rate limiter.
pub trait Clock: Send + Sync + fmt::Debug {
    /// The current instant.
    fn now(&self) -> Instant;
}

/// The real monotonic clock ([`Instant::now`]).
#[derive(Debug, Default, Clone, Copy)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> Instant {
        Instant::now()
    }
}

/// A clock that only moves when told to — for tests and simulations.
///
/// Clones share the same time, so a test can keep one handle and pass
/// another to [`crate::DashboardApp::with_clock`].
#[derive(Debug, Clone)]
pub struct ManualClock {
    start: Instant,
    elapsed: Arc<Mutex<Duration>>,
}

impl ManualClock {
    /// A clock frozen at the moment of creation.
    pub fn new() -> Self {
        Self {
            start: Instant::now(),
            elapsed: Arc::new(Mutex::new(Duration::ZERO)),
        }
    }

    /// Move the clock forward by `by`.
    pub fn advance(&self, by: Duration) {
        let mut elapsed = self.elapsed.lock().unwrap_or_else(PoisonError::into_inner);
        *elapsed += by;
    }
}

impl Default for ManualClock {
    fn default() -> Self {
        Self::new()
    }
}

impl Clock for ManualClock {
    fn now(&self) -> Instant {
        self.start + *self.elapsed.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

// ── RateLimit ────────────────────────────────────────────────────────────────

/// How many memory requests a client may make per time window.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RateLimit {
    max_requests: u32,
    window: Duration,
}

impl RateLimit {
    /// At most `max_requests` per `window`. Both must be non-zero.
    pub fn new(max_requests: u32, window: Duration) -> Result<Self> {
        if max_requests == 0 {
            bail!("rate limit must allow at least 1 request");
        }
        if window.is_zero() {
            bail!("rate limit window must be longer than zero");
        }
        Ok(Self {
            max_requests,
            window,
        })
    }

    /// At most `max_requests` per minute (must be at least 1).
    pub fn per_minute(max_requests: u32) -> Result<Self> {
        Self::new(max_requests, Duration::from_secs(60))
    }

    /// Requests allowed per window.
    pub fn max_requests(&self) -> u32 {
        self.max_requests
    }

    /// Length of one window.
    pub fn window(&self) -> Duration {
        self.window
    }
}

impl Default for RateLimit {
    /// [`DEFAULT_RATE_LIMIT`] requests per minute.
    fn default() -> Self {
        Self {
            max_requests: DEFAULT_RATE_LIMIT,
            window: Duration::from_secs(60),
        }
    }
}

// ── RateLimiter ──────────────────────────────────────────────────────────────

/// One client's current window.
#[derive(Debug, Clone, Copy)]
struct Window {
    started: Instant,
    count: u32,
}

/// Result of [`RateLimiter::check`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Decision {
    /// The request fits into the client's budget.
    Allowed,
    /// The budget is used up until `retry_after` has passed. `first` is true
    /// for the first rejected request of the window (logged at `warn`).
    Limited { retry_after: Duration, first: bool },
}

/// Fixed-window request counter per client IP, bounded in size.
#[derive(Debug)]
pub(crate) struct RateLimiter {
    limit: RateLimit,
    clock: Arc<dyn Clock>,
    capacity: usize,
    clients: Mutex<HashMap<IpAddr, Window>>,
}

impl RateLimiter {
    /// A limiter tracking at most [`MAX_TRACKED_CLIENTS`] clients.
    pub(crate) fn new(limit: RateLimit, clock: Arc<dyn Clock>) -> Self {
        Self::with_capacity(limit, clock, MAX_TRACKED_CLIENTS)
    }

    /// A limiter tracking at most `capacity` (at least 1) clients.
    pub(crate) fn with_capacity(limit: RateLimit, clock: Arc<dyn Clock>, capacity: usize) -> Self {
        Self {
            limit,
            clock,
            capacity: capacity.max(1),
            clients: Mutex::new(HashMap::new()),
        }
    }

    /// The configured limit.
    pub(crate) fn limit(&self) -> RateLimit {
        self.limit
    }

    /// Count one request from `client` and decide whether it may proceed.
    pub(crate) fn check(&self, client: IpAddr) -> Decision {
        let now = self.clock.now();
        let window = self.limit.window;
        let mut clients = self.clients.lock().unwrap_or_else(PoisonError::into_inner);

        if !clients.contains_key(&client) && clients.len() >= self.capacity {
            Self::evict(&mut clients, now, window, self.capacity);
        }
        let entry = clients.entry(client).or_insert(Window {
            started: now,
            count: 0,
        });
        let elapsed = now.saturating_duration_since(entry.started);
        if elapsed >= window {
            *entry = Window {
                started: now,
                count: 0,
            };
        }

        if entry.count < self.limit.max_requests {
            entry.count += 1;
            return Decision::Allowed;
        }
        let first = entry.count == self.limit.max_requests;
        // Saturate instead of overflowing on a client that never stops.
        entry.count = entry.count.saturating_add(1);
        Decision::Limited {
            retry_after: window.saturating_sub(now.saturating_duration_since(entry.started)),
            first,
        }
    }

    /// Make room for one more client: drop expired windows, and if that is
    /// not enough, the client whose window started first.
    fn evict(
        clients: &mut HashMap<IpAddr, Window>,
        now: Instant,
        window: Duration,
        capacity: usize,
    ) {
        clients.retain(|_, w| now.saturating_duration_since(w.started) < window);
        while clients.len() >= capacity {
            let Some(oldest) = clients
                .iter()
                .min_by_key(|(_, w)| w.started)
                .map(|(ip, _)| *ip)
            else {
                break;
            };
            clients.remove(&oldest);
        }
    }

    /// Number of clients currently tracked.
    #[cfg(test)]
    fn tracked(&self) -> usize {
        self.clients
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .len()
    }
}

/// Middleware: apply `limiter` to the request's client IP.
///
/// The IP comes from axum's `ConnectInfo<SocketAddr>` (set by
/// [`crate::BoundServer::run_until`]). Requests without it — a router driven
/// directly, e.g. in tests — share one bucket keyed `0.0.0.0`.
pub(crate) async fn limit_requests(
    State(limiter): State<Arc<RateLimiter>>,
    req: Request,
    next: Next,
) -> Response {
    let client = req
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map_or(IpAddr::V4(Ipv4Addr::UNSPECIFIED), |c| c.0.ip());

    match limiter.check(client) {
        Decision::Allowed => next.run(req).await,
        Decision::Limited { retry_after, first } => {
            let limit = limiter.limit();
            if first {
                warn!(
                    "rate limit exceeded by {client}: more than {} requests per {}s ({} {})",
                    limit.max_requests,
                    limit.window.as_secs(),
                    req.method(),
                    req.uri().path()
                );
            } else {
                debug!(
                    "rate-limited {client}: {} {}",
                    req.method(),
                    req.uri().path()
                );
            }
            let mut res = ApiError::rate_limited(limit).into_response();
            let secs = retry_after.as_secs() + u64::from(retry_after.subsec_nanos() > 0);
            res.headers_mut()
                .insert(header::RETRY_AFTER, HeaderValue::from(secs.max(1)));
            res
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const N: u32 = 5;
    const MINUTE: Duration = Duration::from_secs(60);

    fn ip(last: u8) -> IpAddr {
        IpAddr::V4(Ipv4Addr::new(10, 0, 0, last))
    }

    fn limiter(capacity: usize) -> (RateLimiter, ManualClock) {
        let clock = ManualClock::new();
        let limit = RateLimit::per_minute(N).unwrap();
        (
            RateLimiter::with_capacity(limit, Arc::new(clock.clone()), capacity),
            clock,
        )
    }

    #[test]
    fn n_allowed_then_blocked() {
        let (limiter, _) = limiter(16);
        for i in 0..N {
            assert_eq!(limiter.check(ip(1)), Decision::Allowed, "request {i}");
        }
        assert_eq!(
            limiter.check(ip(1)),
            Decision::Limited {
                retry_after: MINUTE,
                first: true
            }
        );
        assert!(matches!(
            limiter.check(ip(1)),
            Decision::Limited { first: false, .. }
        ));
    }

    #[test]
    fn window_resets_after_it_elapses() {
        let (limiter, clock) = limiter(16);
        for _ in 0..N {
            assert_eq!(limiter.check(ip(1)), Decision::Allowed);
        }
        clock.advance(Duration::from_secs(45));
        assert_eq!(
            limiter.check(ip(1)),
            Decision::Limited {
                retry_after: Duration::from_secs(15),
                first: true
            }
        );
        clock.advance(Duration::from_secs(15));
        for _ in 0..N {
            assert_eq!(limiter.check(ip(1)), Decision::Allowed);
        }
        assert!(matches!(limiter.check(ip(1)), Decision::Limited { .. }));
    }

    #[test]
    fn clients_have_separate_budgets() {
        let (limiter, _) = limiter(16);
        for _ in 0..N {
            limiter.check(ip(1));
        }
        assert!(matches!(limiter.check(ip(1)), Decision::Limited { .. }));
        assert_eq!(limiter.check(ip(2)), Decision::Allowed);
    }

    #[test]
    fn tracked_clients_are_bounded() {
        let (limiter, clock) = limiter(4);
        for last in 0..100 {
            limiter.check(ip(last));
            clock.advance(Duration::from_millis(10));
            assert!(limiter.tracked() <= 4);
        }
        // The most recent client survived eviction and kept its count.
        for _ in 1..N {
            assert_eq!(limiter.check(ip(99)), Decision::Allowed);
        }
        assert!(matches!(limiter.check(ip(99)), Decision::Limited { .. }));
    }

    #[test]
    fn expired_windows_are_evicted_first() {
        let (limiter, clock) = limiter(2);
        limiter.check(ip(1));
        clock.advance(MINUTE);
        // ip(1)'s window has expired; ip(2) and ip(3) are both live.
        limiter.check(ip(2));
        limiter.check(ip(3));
        assert_eq!(limiter.tracked(), 2);
        // ip(2) was not evicted: its count continues.
        for _ in 1..N {
            assert_eq!(limiter.check(ip(2)), Decision::Allowed);
        }
        assert!(matches!(limiter.check(ip(2)), Decision::Limited { .. }));
    }

    #[test]
    fn invalid_limits_are_rejected() {
        assert!(RateLimit::per_minute(0).is_err());
        assert!(RateLimit::new(1, Duration::ZERO).is_err());
        assert_eq!(RateLimit::default(), RateLimit::per_minute(60).unwrap());
    }
}
