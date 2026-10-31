//! Security headers added to every response (HTML, assets, JSON, errors).
//!
//! - `Content-Security-Policy`: the embedded page may load only its own
//!   script, stylesheet and API (no inline code, no third parties, no
//!   framing); every other response gets a policy that allows nothing.
//! - `X-Content-Type-Options: nosniff`, so JSON is never sniffed as script.
//! - `Referrer-Policy: no-referrer`, so dashboard URLs (pids, addresses)
//!   never leak to other sites.
//! - `X-Frame-Options: DENY` (legacy twin of `frame-ancestors 'none'`),
//!   `Cross-Origin-Resource-Policy: same-origin` (no cross-site embedding via
//!   `<script>` / `<img>`) and `Cache-Control: no-store` (memory contents
//!   must not end up in a cache).

use axum::extract::Request;
use axum::http::{HeaderMap, HeaderName, HeaderValue, header};
use axum::middleware::Next;
use axum::response::Response;

/// CSP for the embedded dashboard page (`index.html`). The page uses only
/// `/app.js`, `/app.css` and `fetch` to `/api/*` on its own origin.
pub(crate) const PAGE_CSP: &str = "default-src 'none'; script-src 'self'; style-src 'self'; \
    connect-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; \
    frame-ancestors 'none'";

/// CSP for every non-HTML response: nothing may run in or embed it.
pub(crate) const RESOURCE_CSP: &str = "default-src 'none'; frame-ancestors 'none'; sandbox";

const CROSS_ORIGIN_RESOURCE_POLICY: HeaderName =
    HeaderName::from_static("cross-origin-resource-policy");

/// Middleware: add the security headers to the response of `req`.
pub(crate) async fn security_headers(req: Request, next: Next) -> Response {
    let mut res = next.run(req).await;
    let headers = res.headers_mut();
    let csp = if is_html(headers) {
        PAGE_CSP
    } else {
        RESOURCE_CSP
    };
    let fixed = [
        (header::CONTENT_SECURITY_POLICY, csp),
        (header::X_CONTENT_TYPE_OPTIONS, "nosniff"),
        (header::REFERRER_POLICY, "no-referrer"),
        (header::X_FRAME_OPTIONS, "DENY"),
        (CROSS_ORIGIN_RESOURCE_POLICY, "same-origin"),
        (header::CACHE_CONTROL, "no-store"),
    ];
    for (name, value) in fixed {
        headers.insert(name, HeaderValue::from_static(value));
    }
    res
}

fn is_html(headers: &HeaderMap) -> bool {
    headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|ct| ct.starts_with("text/html"))
}
