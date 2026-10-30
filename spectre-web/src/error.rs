//! JSON response envelope and API error type.

use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Serialize;

/// Successful API response: `{ "ok": true, "data": ... }`.
#[derive(Debug, Serialize)]
pub(crate) struct ApiOk<T: Serialize> {
    ok: bool,
    data: T,
}

/// Wrap `data` in the success envelope.
pub(crate) fn ok<T: Serialize>(data: T) -> Json<ApiOk<T>> {
    Json(ApiOk { ok: true, data })
}

/// Failed API response, rendered as `{ "ok": false, "error": "..." }`.
///
/// Messages are written by this crate only — backend error text (which may
/// contain filesystem paths, device serials, ...) is logged, never returned.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    /// 400 — a query parameter is missing or invalid.
    pub fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    /// 502 — the memory backend (OS / ADB) failed to serve the request.
    pub fn backend(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_GATEWAY,
            message: message.into(),
        }
    }

    /// 404 — no such route.
    pub fn not_found() -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            message: "not found".to_owned(),
        }
    }

    /// 405 — the route exists but only accepts `GET` (the API is read-only).
    pub fn method_not_allowed() -> Self {
        Self {
            status: StatusCode::METHOD_NOT_ALLOWED,
            message: "method not allowed (read-only API, use GET)".to_owned(),
        }
    }

    /// 403 — the request did not come from the dashboard's own origin
    /// (foreign `Host`, cross-origin `Origin` or `Sec-Fetch-Site`).
    pub fn forbidden(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::FORBIDDEN,
            message: message.into(),
        }
    }

    /// 429 — too many expensive requests (searches) are already running.
    pub fn busy(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::TOO_MANY_REQUESTS,
            message: message.into(),
        }
    }

    /// 500 — unexpected server-side failure (e.g. a panicked worker task).
    pub fn internal() -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: "internal error".to_owned(),
        }
    }

    /// HTTP status of this error.
    pub fn status(&self) -> StatusCode {
        self.status
    }

    /// Client-facing error message.
    pub fn message(&self) -> &str {
        &self.message
    }
}

#[derive(Serialize)]
struct ApiErrBody<'a> {
    ok: bool,
    error: &'a str,
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let body = ApiErrBody {
            ok: false,
            error: &self.message,
        };
        (self.status, Json(body)).into_response()
    }
}
