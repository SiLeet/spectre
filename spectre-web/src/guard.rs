//! Same-origin guard: defence against DNS rebinding and cross-site requests.
//!
//! Binding to `127.0.0.1` keeps other machines out, but not other *websites*:
//! a page the user visits can rebind its own hostname to `127.0.0.1` and then
//! talk to the dashboard as a same-origin request (CORS does not apply), or
//! fire blind cross-site `GET`s (`<img src>`, `fetch(.., {mode: "no-cors"})`).
//! Every request therefore has to pass three checks:
//!
//! 1. `Host` (or the URI authority) must name a loopback host — `127.0.0.1`,
//!    `localhost` or `[::1]`, any port. A rebinding attacker cannot make the
//!    browser send one of these for its own origin. Requests without any host
//!    (raw HTTP/1.0 tools) are allowed; browsers always send `Host`.
//! 2. `Origin`, when present, must be an `http://` loopback origin (`null`
//!    is rejected).
//! 3. For `/api/*`, `Sec-Fetch-Site`, when present, must be `same-origin` or
//!    `none` (typed into the address bar). This stops cross-site `GET`s that
//!    carry no `Origin` header. UI routes skip this check so that following a
//!    link to the dashboard from another page still works.

use axum::extract::Request;
use axum::http::uri::Authority;
use axum::http::{HeaderMap, HeaderName, Uri, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use tracing::warn;

use crate::error::ApiError;

/// `Sec-Fetch-Site` request header (Fetch Metadata).
const SEC_FETCH_SITE: HeaderName = HeaderName::from_static("sec-fetch-site");

/// Hostnames under which the dashboard may legitimately be addressed.
const LOOPBACK_HOSTS: [&str; 3] = ["127.0.0.1", "localhost", "[::1]"];

/// Middleware: reject requests that do not originate from the dashboard
/// itself (see the module docs) with a JSON 403.
pub(crate) async fn same_origin_only(req: Request, next: Next) -> Response {
    if let Err(e) = check(req.headers(), req.uri()) {
        warn!(
            "rejected {} {}: {}",
            req.method(),
            req.uri().path(),
            e.message()
        );
        return e.into_response();
    }
    next.run(req).await
}

/// Validate `Host`, `Origin` and (for API paths) `Sec-Fetch-Site`.
fn check(headers: &HeaderMap, uri: &Uri) -> Result<(), ApiError> {
    let host = match headers.get(header::HOST) {
        Some(v) => Some(
            v.to_str()
                .ok()
                .and_then(|s| s.parse::<Authority>().ok())
                .ok_or_else(|| ApiError::forbidden("forbidden: malformed Host header"))?,
        ),
        None => uri.authority().cloned(),
    };
    if let Some(host) = host
        && !is_loopback_host(host.host())
    {
        return Err(ApiError::forbidden(
            "forbidden: unexpected Host header (open the dashboard via http://127.0.0.1:<port>/)",
        ));
    }

    if let Some(origin) = headers.get(header::ORIGIN) {
        let allowed = origin
            .to_str()
            .ok()
            .and_then(|s| s.parse::<Uri>().ok())
            .is_some_and(|o| {
                o.scheme_str() == Some("http")
                    && o.authority().is_some_and(|a| is_loopback_host(a.host()))
            });
        if !allowed {
            return Err(ApiError::forbidden("forbidden: cross-origin request"));
        }
    }

    if uri.path().starts_with("/api/")
        && let Some(site) = headers.get(SEC_FETCH_SITE)
        && !matches!(site.as_bytes(), b"same-origin" | b"none")
    {
        return Err(ApiError::forbidden("forbidden: cross-site request"));
    }
    Ok(())
}

fn is_loopback_host(host: &str) -> bool {
    LOOPBACK_HOSTS.iter().any(|h| host.eq_ignore_ascii_case(h))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    fn run(path: &str, pairs: &[(HeaderName, &str)]) -> Result<(), ApiError> {
        let mut headers = HeaderMap::new();
        for (name, value) in pairs {
            headers.insert(name.clone(), HeaderValue::from_str(value).unwrap());
        }
        check(&headers, &path.parse().unwrap())
    }

    #[test]
    fn loopback_hosts_pass() {
        for host in [
            "127.0.0.1:8787",
            "localhost:8787",
            "LOCALHOST",
            "[::1]:8787",
        ] {
            assert!(run("/api/info", &[(header::HOST, host)]).is_ok(), "{host}");
        }
        assert!(run("/api/info", &[]).is_ok(), "no Host at all");
    }

    #[test]
    fn foreign_hosts_are_rejected() {
        for host in [
            "evil.example",
            "attacker.example:8787",
            "127.0.0.1.evil.example",
            "localhost.evil.example:8787",
            "",
        ] {
            let err = run("/api/processes", &[(header::HOST, host)]).unwrap_err();
            assert_eq!(err.status(), axum::http::StatusCode::FORBIDDEN, "{host}");
        }
        // Absolute-form request target with a foreign authority.
        assert!(run("http://evil.example/api/info", &[]).is_err());
    }

    #[test]
    fn origin_must_be_loopback_http() {
        let host = (header::HOST, "127.0.0.1:8787");
        let ok = |o| run("/api/info", &[host.clone(), (header::ORIGIN, o)]).is_ok();
        assert!(ok("http://127.0.0.1:8787"));
        assert!(ok("http://localhost:8787"));
        assert!(!ok("https://evil.example"));
        assert!(!ok("http://evil.example:8787"));
        assert!(!ok("null"));
        assert!(!ok("file://localhost"));
    }

    #[test]
    fn sec_fetch_site_guards_api_only() {
        let host = (header::HOST, "127.0.0.1:8787");
        let site = |path, v| run(path, &[host.clone(), (SEC_FETCH_SITE, v)]).is_ok();
        assert!(site("/api/search", "same-origin"));
        assert!(site("/api/search", "none"));
        assert!(!site("/api/search", "cross-site"));
        assert!(!site("/api/read", "same-site"));
        // Following a link to the UI from another site is fine.
        assert!(site("/", "cross-site"));
    }
}
