//! Spectre Web — read-only local web dashboard (`spectre serve`).
//!
//! Serves an embedded single-page UI plus a small JSON API on
//! `127.0.0.1` only:
//!
//! | Route | Purpose |
//! |-------|---------|
//! | `GET /` | embedded HTML dashboard (plus `/app.js`, `/app.css`) |
//! | `GET /api/info` | crate version, backend kind and request limits |
//! | `GET /api/processes[?name=S]` | all (or name-filtered) processes |
//! | `GET /api/regions?pid=N[&perms=S]` | memory regions of a process |
//! | `GET /api/read?pid=N&addr=A&type=T[&size=S][&endian=E]` | read one value |
//! | `GET /api/search?pid=N&type=T&value=V[&limit=L][&endian=E]` | exact-value search |
//!
//! Every API response is `{ "ok": true, "data": ... }` or
//! `{ "ok": false, "error": "..." }`. Error messages are generic and never
//! contain backend details such as filesystem paths or environment values;
//! those are only logged via `tracing`.
//!
//! The API is strictly read-only: every route is `GET` (`HEAD`), other
//! methods get a JSON 405, and there are no endpoints that write memory or
//! start anything.
//!
//! # Access control
//!
//! - The server binds `127.0.0.1` only; there is deliberately no way to bind
//!   another interface.
//! - Every request passes an origin guard (`Host` must be
//!   `127.0.0.1:PORT` / `localhost:PORT`, plus `Origin` and `Sec-Fetch-Site`
//!   checks) so that websites cannot reach the API through DNS rebinding or
//!   blind cross-site requests. CORS is off unless origins are allow-listed
//!   with [`DashboardApp::with_allowed_origins`]; `*` is never sent.
//! - `/api/read` and `/api/search` are rate-limited per client
//!   ([`RateLimit`], default [`DEFAULT_RATE_LIMIT`] per minute); all loopback
//!   peers share one budget.
//! - Searches are limited to [`MAX_CONCURRENT_SEARCHES`] at a time and stop
//!   reading memory once their client disconnects.
//! - Every response carries security headers (`Content-Security-Policy`,
//!   `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, ...).
//!
//! # Concurrency model
//!
//! [`MemoryReader`] is `Send + Sync`, so a single reader is shared by all
//! handlers through an `Arc<dyn MemoryReader>` — no `Mutex` is needed, and
//! backends that need interior state synchronise it themselves. Reader calls
//! are blocking (`ReadProcessMemory`, `/proc/<pid>/mem`, `adb` subprocesses),
//! so every handler runs them on tokio's blocking pool via
//! [`tokio::task::spawn_blocking`].
//!
//! # Extending
//!
//! [`router`] returns a plain [`axum::Router`] (with all hardening layers
//! already applied) so callers such as tests can drive it without a socket
//! or wrap it in further middleware. Configure the app first with
//! [`DashboardApp::with_port`], [`DashboardApp::with_rate_limit`],
//! [`DashboardApp::with_allowed_origins`] and [`DashboardApp::with_clock`].

mod cancel;
mod error;
mod guard;
mod headers;
mod params;
mod ratelimit;
mod routes;

use std::future::Future;
use std::net::{Ipv4Addr, SocketAddr};
use std::sync::Arc;

use anyhow::{Context, Result};
use axum::Router;
use spectre_core::MemoryReader;
use tokio::net::TcpListener;
use tokio::sync::Semaphore;
use tracing::{info, warn};

pub use error::ApiError;
pub use ratelimit::{
    Clock, DEFAULT_RATE_LIMIT, MAX_TRACKED_CLIENTS, ManualClock, RateLimit, SystemClock,
};
pub use routes::router;

use guard::Guard;
use ratelimit::RateLimiter;

/// Default port of `spectre serve`.
pub const DEFAULT_PORT: u16 = 8787;
/// Largest number of bytes a single `/api/read` request may fetch.
pub const MAX_READ_SIZE: u32 = 4096;
/// Default `size` for `string` / `bytes` reads.
pub const DEFAULT_READ_SIZE: u32 = 64;
/// Default number of addresses returned by `/api/search`.
pub const DEFAULT_SEARCH_LIMIT: u32 = 1000;
/// Hard upper bound for the `/api/search` `limit` parameter.
pub const MAX_SEARCH_LIMIT: u32 = 10_000;
/// Number of `/api/search` scans that may run at once; further searches are
/// answered with 429 until one finishes.
pub const MAX_CONCURRENT_SEARCHES: usize = 2;

/// Shared state of the dashboard: the injected memory reader, the search
/// concurrency budget, the rate limiter and the origin guard settings.
///
/// Clones share the search budget and the rate limiter. Configure the app
/// with the `with_*` methods *before* building routers from it.
#[derive(Debug, Clone)]
pub struct DashboardApp {
    reader: Arc<dyn MemoryReader>,
    search_slots: Arc<Semaphore>,
    clock: Arc<dyn Clock>,
    limiter: Arc<RateLimiter>,
    guard: Guard,
}

impl DashboardApp {
    /// Create a dashboard backed by `reader` (native, ADB, dump file, fake...)
    /// with the default rate limit, no extra CORS origins and the system clock.
    pub fn new(reader: Arc<dyn MemoryReader>) -> Self {
        let clock: Arc<dyn Clock> = Arc::new(SystemClock);
        Self {
            reader,
            search_slots: Arc::new(Semaphore::new(MAX_CONCURRENT_SEARCHES)),
            limiter: Arc::new(RateLimiter::new(RateLimit::default(), Arc::clone(&clock))),
            clock,
            guard: Guard::default(),
        }
    }

    /// Limit `/api/read` + `/api/search` to `limit` per client, with all
    /// loopback peers counting as one (replaces the limiter, i.e. resets all
    /// counters).
    pub fn with_rate_limit(mut self, limit: RateLimit) -> Self {
        self.limiter = Arc::new(RateLimiter::new(limit, Arc::clone(&self.clock)));
        self
    }

    /// Use `clock` as the rate limiter's time source (e.g. a
    /// [`ManualClock`] in tests). Resets all rate-limit counters.
    pub fn with_clock(mut self, clock: Arc<dyn Clock>) -> Self {
        self.clock = clock;
        let limit = self.limiter.limit();
        self.with_rate_limit(limit)
    }

    /// Allow these extra origins (e.g. `https://tool.example`,
    /// `http://localhost:3000`) to call the API cross-origin (CORS).
    ///
    /// Each entry must be `http(s)://host[:port]` without path; `*`, `null`
    /// and other wildcards are rejected. An empty list (the default) means
    /// same-origin only. Replaces any previous list.
    pub fn with_allowed_origins<I, S>(mut self, origins: I) -> Result<Self>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        self.guard = self.guard.with_allowed_origins(origins)?;
        Ok(self)
    }

    /// Only accept requests whose `Host` (and same-origin `Origin`) names
    /// this port. [`DashboardApp::bind`] sets it to the bound port
    /// automatically; without it, a bare [`router`] accepts any port.
    pub fn with_port(mut self, port: u16) -> Self {
        self.guard = self.guard.with_port(port);
        self
    }

    /// The reader every request is served from.
    pub fn reader(&self) -> &Arc<dyn MemoryReader> {
        &self.reader
    }

    /// The configured per-client rate limit for the memory endpoints.
    pub fn rate_limit(&self) -> RateLimit {
        self.limiter.limit()
    }

    /// The configured CORS allow-list (normalised, without default ports).
    pub fn allowed_origins(&self) -> &[String] {
        self.guard.allowed_origins()
    }

    /// Permits for concurrently running searches.
    pub(crate) fn search_slots(&self) -> &Arc<Semaphore> {
        &self.search_slots
    }

    /// The shared rate limiter of the memory endpoints.
    pub(crate) fn limiter(&self) -> &Arc<RateLimiter> {
        &self.limiter
    }

    /// The origin guard settings.
    pub(crate) fn guard(&self) -> &Guard {
        &self.guard
    }

    /// Bind `127.0.0.1:port` without serving yet. Port `0` picks a free port;
    /// use [`BoundServer::local_addr`] to learn which one. The origin guard
    /// is pinned to the bound port.
    pub async fn bind(self, port: u16) -> Result<BoundServer> {
        let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
        let listener = TcpListener::bind(addr)
            .await
            .with_context(|| format!("cannot bind dashboard to {addr}"))?;
        let local_addr = listener
            .local_addr()
            .context("cannot determine dashboard listen address")?;
        Ok(BoundServer {
            listener,
            router: router(self.with_port(local_addr.port())),
            local_addr,
        })
    }

    /// Bind `127.0.0.1:port`, print the dashboard URL and serve until Ctrl+C.
    pub async fn serve(self, port: u16) -> Result<()> {
        let limit = self.rate_limit();
        let origins = self.allowed_origins().join(", ");
        let server = self.bind(port).await?;
        println!("Spectre dashboard: {}", server.url());
        println!("(read-only, bound to 127.0.0.1; press Ctrl+C to stop)");
        println!(
            "rate limit: {} memory requests per {} s per client",
            limit.max_requests(),
            limit.window().as_secs()
        );
        if !origins.is_empty() {
            println!("CORS allowed origins: {origins}");
        }
        server.run_until(shutdown_signal()).await
    }
}

/// A dashboard whose listener is bound but not yet accepting requests.
#[derive(Debug)]
pub struct BoundServer {
    listener: TcpListener,
    router: Router,
    local_addr: SocketAddr,
}

impl BoundServer {
    /// The actual address the server listens on (resolves port `0`).
    pub fn local_addr(&self) -> SocketAddr {
        self.local_addr
    }

    /// Dashboard URL, e.g. `http://127.0.0.1:8787/`.
    pub fn url(&self) -> String {
        format!("http://{}/", self.local_addr)
    }

    /// Serve requests until `shutdown` completes, then drain gracefully.
    pub async fn run_until<F>(self, shutdown: F) -> Result<()>
    where
        F: Future<Output = ()> + Send + 'static,
    {
        info!("dashboard listening on {}", self.local_addr);
        // Connect info supplies the client IP for per-client rate limiting.
        let service = self
            .router
            .into_make_service_with_connect_info::<SocketAddr>();
        axum::serve(self.listener, service)
            .with_graceful_shutdown(shutdown)
            .await
            .context("dashboard server failed")?;
        info!("dashboard stopped");
        Ok(())
    }
}

/// Resolve on Ctrl+C. If the handler cannot be installed, never resolve
/// (the process can still be killed) instead of shutting down immediately.
async fn shutdown_signal() {
    if let Err(e) = tokio::signal::ctrl_c().await {
        warn!("cannot listen for Ctrl+C: {e}");
        std::future::pending::<()>().await;
    }
}
