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
//! `{ "ok": false, "error": "..." }`. Error messages never contain backend
//! details such as filesystem paths; those are only logged via `tracing`.
//!
//! # Access control
//!
//! Besides the loopback bind, every request passes a same-origin guard
//! (`Host`, `Origin`, `Sec-Fetch-Site`) so that websites cannot reach the
//! API through DNS rebinding or blind cross-site requests. Searches are
//! limited to [`MAX_CONCURRENT_SEARCHES`] at a time and stop reading memory
//! once their client disconnects.
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
//! [`router`] returns a plain [`axum::Router`] so callers (tests, or a later
//! hardening layer) can drive it without a socket or wrap it in middleware.

mod cancel;
mod error;
mod guard;
mod params;
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
pub use routes::router;

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

/// Shared state of the dashboard: the injected memory reader and the
/// search concurrency budget.
#[derive(Debug, Clone)]
pub struct DashboardApp {
    reader: Arc<dyn MemoryReader>,
    search_slots: Arc<Semaphore>,
}

impl DashboardApp {
    /// Create a dashboard backed by `reader` (native, ADB, dump file, fake...).
    pub fn new(reader: Arc<dyn MemoryReader>) -> Self {
        Self {
            reader,
            search_slots: Arc::new(Semaphore::new(MAX_CONCURRENT_SEARCHES)),
        }
    }

    /// The reader every request is served from.
    pub fn reader(&self) -> &Arc<dyn MemoryReader> {
        &self.reader
    }

    /// Permits for concurrently running searches.
    pub(crate) fn search_slots(&self) -> &Arc<Semaphore> {
        &self.search_slots
    }

    /// Bind `127.0.0.1:port` without serving yet. Port `0` picks a free port;
    /// use [`BoundServer::local_addr`] to learn which one.
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
            router: router(self),
            local_addr,
        })
    }

    /// Bind `127.0.0.1:port`, print the dashboard URL and serve until Ctrl+C.
    pub async fn serve(self, port: u16) -> Result<()> {
        let server = self.bind(port).await?;
        println!("Spectre dashboard: {}", server.url());
        println!("(read-only, bound to 127.0.0.1; press Ctrl+C to stop)");
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
        axum::serve(self.listener, self.router)
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
