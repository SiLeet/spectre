# spectre-web

Read-only local web dashboard for Spectre, started with `spectre serve`.

```bash
spectre serve              # http://127.0.0.1:8787/
spectre serve --port 0     # pick a free port; the real URL is printed
spectre serve --adb        # use the ADB backend instead of the native one
spectre serve --rate-limit 120 --allow-origin http://localhost:3000
```

The server binds **127.0.0.1 only**, offers **only `GET` endpoints** (no
writes, no bot control, no execution), and embeds its HTML/JS/CSS in the
binary — no CDN, works offline.

There is deliberately **no `--host` flag**: the API exposes process memory
without authentication, so it must never listen on a network interface.
Use an SSH tunnel (`ssh -L 8787:127.0.0.1:8787 <host>`) for remote access.

| Option | Default | Meaning |
|--------|---------|---------|
| `--port <p>` | 8787 | listen port on 127.0.0.1 (`0` = any free port) |
| `--rate-limit <n>` | 60 | `/api/read` + `/api/search` requests per minute and client (≥ 1) |
| `--allow-origin <origin>` | none | extra origin allowed via CORS (repeatable, no wildcards) |

The UI: process list with filter → region table of the selected process →
read form → value search. Clicking a region or a search hit fills the read
form.

## Endpoints

Every API response is either

```json
{ "ok": true,  "data": ... }
{ "ok": false, "error": "human readable message" }
```

| Endpoint | Parameters | `data` |
|----------|------------|--------|
| `GET /` | — | embedded dashboard (also `/app.js`, `/app.css`) |
| `GET /api/info` | — | `{ name, version, backend, max_read_size, default_search_limit, max_search_limit, rate_limit_max_requests, rate_limit_window_secs }` |
| `GET /api/processes` | `name` (optional substring, case-insensitive) | `[{ pid, name }]`, sorted by pid |
| `GET /api/regions` | `pid` (required), `perms` (optional substring, e.g. `rw`) | `[{ start, end, size, perms, path }]`; `start`/`end` are `0x` hex strings |
| `GET /api/read` | `pid`, `addr` (`0x` hex or decimal), `type`, `size`, `endian` | `{ pid, address, type, size, endian, value, hex }` |
| `GET /api/search` | `pid`, `type`, `value`, `limit`, `endian` | `{ pid, type, value, limit, count, truncated, addresses }` |

### `/api/read`

- `type`: `u8` `u16` `u32` `u64` `i8` `i16` `i32` `i64` `f32` `f64` `string` `bytes`.
- `size`: only used by `string` (max length, stops at the first NUL) and
  `bytes`; default 64, **at most 4096**.
- `endian`: `little` (default) or `big`.
- `value` is a JSON number, except: `u64`/`i64` are decimal strings (JavaScript
  numbers cannot hold them exactly), non-finite floats are strings, and
  `bytes` is a hex string. `hex` always holds the raw bytes.

### `/api/search`

- `type`: numeric types only; `value`: decimal (negative for `i*`), `0x` hex,
  or a float for `f32`/`f64`.
- Scans readable+writable (`rw`) regions at natural alignment, like
  `spectre search`.
- `limit`: default **1000**, between 1 and **10000**. `truncated: true` means
  more matches exist than were returned.
- At most **2** searches run at the same time; more return 429. A search stops
  reading memory as soon as its client disconnects.

### Access control

Binding to 127.0.0.1 keeps other machines out but not other websites, which
could reach the API through DNS rebinding or blind cross-site `GET`s. Every
request is therefore checked:

- `Host` must be `127.0.0.1:<port>` or `localhost:<port>` with the port the
  server is bound to (`[::1]` is refused — the server listens on IPv4 only).
- `Origin`, if sent, must be the dashboard's own origin
  (`http://127.0.0.1:<port>` / `http://localhost:<port>`) or an allowed
  origin (see CORS). `null` is always refused.
- For `/api/*` requests not from an allowed origin, `Sec-Fetch-Site`, if
  sent, must be `same-origin` or `none`.

Anything else is answered with 403.

### CORS

Off by default: the API is same-origin only and sends no
`Access-Control-*` headers. Each `--allow-origin` (library:
`DashboardApp::with_allowed_origins`) adds one exact origin,
`http(s)://host[:port]` without path. Requests from it get
`Access-Control-Allow-Origin: <that origin>` (never `*`, no credentials) and
`Vary: Origin`; its preflights (including Chrome's Private Network Access
preflight) are answered for `GET`/`HEAD` only. Wildcards and `null` are
rejected at startup.

### Rate limiting

`/api/read` and `/api/search` share a per-client-IP budget of 60 requests per
minute (`--rate-limit`, library: `DashboardApp::with_rate_limit`). The
window starts with a client's first request. Beyond the budget the server
answers 429 `{ ok: false, error: "rate limit exceeded: ..." }` with a
`Retry-After` header and logs a `tracing::warn` (once per window and
client). The listing endpoints and the UI are not limited. The limiter keeps
state for at most 1024 clients; expired windows, then the oldest ones, are
evicted. Its clock is injectable (`DashboardApp::with_clock`, `ManualClock`)
for tests.

### Security headers

Every response carries `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
`Cross-Origin-Resource-Policy: same-origin` and `Cache-Control: no-store`.
The page gets `Content-Security-Policy: default-src 'none'; script-src 'self';
style-src 'self'; connect-src 'self'; img-src 'self'; form-action 'self';
base-uri 'none'; frame-ancestors 'none'` (no inline code anywhere); all other
responses get `default-src 'none'; frame-ancestors 'none'; sandbox`.

### Errors

| Status | When |
|--------|------|
| 400 | missing/invalid parameter, `size` or `limit` out of range, malformed query |
| 403 | foreign `Host`/port, cross-origin `Origin` or cross-site `Sec-Fetch-Site` |
| 404 | unknown route |
| 405 | non-`GET` method on an existing route (`Allow: GET,HEAD` is set) |
| 429 | rate limit exceeded (`Retry-After` set), or too many searches running at once |
| 502 | the backend failed: unreadable address, unknown pid, ADB offline, ... |
| 500 | unexpected internal failure |

Error messages are generic and generated by this crate (`read failed`,
`search failed`, `failed to list memory regions`, ...). They never include
backend error text, filesystem paths or environment values; details are
logged via `tracing` (run `spectre -vv serve` to see them).

## Library use

```rust
use std::sync::Arc;
use spectre_web::{DashboardApp, RateLimit};

let app = DashboardApp::new(Arc::new(my_reader)) // any MemoryReader
    .with_rate_limit(RateLimit::per_minute(120)?)
    .with_allowed_origins(["http://localhost:3000"])?;
let router = spectre_web::router(app.clone());    // plain axum::Router, e.g. for tests
app.serve(8787).await?;                           // binds 127.0.0.1:8787 until Ctrl+C
```

`DashboardApp::bind(port)` returns a `BoundServer` with `local_addr()`,
`url()` and `run_until(shutdown_future)` for embedding and tests; it pins
the `Host` check to the bound port. A bare `router(app)` accepts any port
unless `app.with_port(port)` was called. Requests driven through the router
without a socket share one rate-limit bucket unless they carry
`ConnectInfo<SocketAddr>`.

`MemoryReader` is `Send + Sync`, so one reader is shared by all requests via
`Arc` (no `Mutex`). Reader calls are blocking and run on tokio's blocking
pool (`spawn_blocking`).

The router is assembled from three groups in `src/routes.rs` — UI assets,
listing endpoints (`/api/info`, `/api/processes`, `/api/regions`) and memory
endpoints (`/api/read`, `/api/search`). Layers, outermost first: security
headers (`src/headers.rs`) → origin guard + CORS (`src/guard.rs`, all
routes) → rate limiter (`src/ratelimit.rs`, memory endpoints only), so
requests refused by the guard never use up rate-limit budget.
