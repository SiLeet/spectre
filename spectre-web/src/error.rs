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
