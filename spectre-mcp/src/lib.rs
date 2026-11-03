//! stdio MCP server (JSON-RPC 2.0, one message per line) that exposes the
//! spectre CLI and adb as typed tools.
//!
//! The server is the only adb owner: every external command runs under one
//! mutex, and after every spectre command `adb connect <SERIAL>` is issued,
//! because spectre may restart the adb server.

use std::io::Read;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::sync::mpsc;
use std::time::{Duration, Instant};

use serde_json::{Value, json};

const DEFAULT_PROTOCOL: &str = "2025-06-18";
const DEVICE_HINT: &str =
    " — kein Device: scripts/bluestacks-ensure.sh starten, dann health prüfen";

// ── Config ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct Config {
    pub spectre_bin: String,
    pub adb_bin: String,
    pub serial: String,
    pub timeout: Duration,
}

impl Config {
    pub fn from_env() -> Self {
        let var = |k: &str| std::env::var(k).ok().filter(|v| !v.is_empty());
        let default_spectre = if cfg!(windows) {
            "target/release/spectre.exe"
        } else {
            "target/release/spectre"
        };
        let default_adb = match var("LOCALAPPDATA") {
            Some(base) => format!("{base}/Android/Sdk/platform-tools/adb.exe"),
            None => "adb".to_owned(),
        };
        let secs = var("CMD_TIMEOUT_SECONDS")
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(120);
        Self {
            spectre_bin: var("SPECTRE_BIN").unwrap_or_else(|| default_spectre.to_owned()),
            adb_bin: var("ADB_BIN").unwrap_or(default_adb),
            serial: var("SERIAL").unwrap_or_else(|| "127.0.0.1:5555".to_owned()),
            timeout: Duration::from_secs(secs),
        }
    }

    /// `host`/`port` of the serial for the subcommands that take `--adb-host/--adb-port`.
    fn host_port(&self) -> (&str, &str) {
        self.serial
            .rsplit_once(':')
            .unwrap_or((&self.serial, "5555"))
    }
}

// ── Command runner ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Default)]
pub struct Output {
    pub code: Option<i32>,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}

impl Output {
    pub fn success(&self) -> bool {
        self.code == Some(0)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum RunError {
    Spawn(String),
    Timeout,
}

pub trait CommandRunner {
    fn run(
        &mut self,
        program: &str,
        args: &[String],
        timeout: Duration,
    ) -> Result<Output, RunError>;
}

/// Runs real processes; kills them when `timeout` passes.
pub struct SystemRunner;

impl CommandRunner for SystemRunner {
    fn run(
        &mut self,
        program: &str,
        args: &[String],
        timeout: Duration,
    ) -> Result<Output, RunError> {
        let deadline = Instant::now() + timeout;
        let mut child = Command::new(program)
            .args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| RunError::Spawn(e.to_string()))?;
        let pipe = |mut r: Box<dyn Read + Send>| {
            let (tx, rx) = mpsc::channel();
            std::thread::spawn(move || {
                let mut buf = Vec::new();
                let _ = r.read_to_end(&mut buf);
                let _ = tx.send(buf);
            });
            rx
        };
        let out_rx = pipe(Box::new(child.stdout.take().expect("piped stdout")));
        let err_rx = pipe(Box::new(child.stderr.take().expect("piped stderr")));
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if Instant::now() >= deadline => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(RunError::Timeout);
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => return Err(RunError::Spawn(e.to_string())),
            }
        };
        // A spawned adb daemon can inherit the pipes and keep them open, so
        // collecting the output is bounded by the same deadline.
        let left = || {
            deadline
                .saturating_duration_since(Instant::now())
                .max(Duration::from_millis(200))
        };
        let stdout = out_rx.recv_timeout(left()).map_err(|_| RunError::Timeout)?;
        let stderr = err_rx.recv_timeout(left()).unwrap_or_default();
        Ok(Output {
            code: status.code(),
            stdout,
            stderr,
        })
    }
}

// ── Server ───────────────────────────────────────────────────────────────────

pub struct Server<R> {
    config: Config,
    runner: Mutex<R>,
}

impl<R: CommandRunner> Server<R> {
    pub fn new(config: Config, runner: R) -> Self {
        Self {
            config,
            runner: Mutex::new(runner),
        }
    }

    /// Handle one input line; `None` for notifications and client responses.
    pub fn handle_line(&self, line: &str) -> Option<String> {
        match serde_json::from_str::<Value>(line) {
            Ok(msg) => self.handle(&msg).map(|v| v.to_string()),
            Err(e) => {
                Some(rpc_error(Value::Null, -32700, &format!("parse error: {e}")).to_string())
            }
        }
    }

    pub fn handle(&self, msg: &Value) -> Option<Value> {
        let id = msg.get("id")?.clone();
        let method = msg.get("method")?.as_str().unwrap_or_default();
        let params = msg.get("params").cloned().unwrap_or(Value::Null);
        let result = match method {
            "initialize" => Ok(json!({
                "protocolVersion": params
                    .get("protocolVersion")
                    .and_then(Value::as_str)
                    .unwrap_or(DEFAULT_PROTOCOL),
                "capabilities": { "tools": {} },
                "serverInfo": { "name": "spectre-mcp", "version": env!("CARGO_PKG_VERSION") },
            })),
            "ping" => Ok(json!({})),
            "tools/list" => Ok(json!({ "tools": tool_list() })),
            "tools/call" => self.call(&params),
            other => Err((-32601, format!("method not found: {other}"))),
        };
        Some(match result {
            Ok(result) => json!({ "jsonrpc": "2.0", "id": id, "result": result }),
            Err((code, message)) => rpc_error(id, code, &message),
        })
    }

    fn call(&self, params: &Value) -> Result<Value, (i64, String)> {
        let name = params
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !tool_list().iter().any(|t| t["name"] == name) {
            return Err((-32602, format!("unknown tool: {name}")));
        }
        let empty = json!({});
        let args = params
            .get("arguments")
            .filter(|a| a.is_object())
            .unwrap_or(&empty);
        let mut runner = self.runner.lock().unwrap_or_else(|e| e.into_inner());
        let mut ctx = Ctx {
            cfg: &self.config,
            r: &mut *runner,
        };
        let outcome = ctx.tool(name, args);
        if let Err(e) = &outcome {
            eprintln!("spectre-mcp: {name}: {e}");
        }
        Ok(match outcome {
            Ok(v) => {
                json!({ "content": [{ "type": "text", "text": pretty(&v) }], "isError": false })
            }
            Err(e) => json!({ "content": [{ "type": "text", "text": e }], "isError": true }),
        })
    }
}

fn rpc_error(id: Value, code: i64, message: &str) -> Value {
    json!({ "jsonrpc": "2.0", "id": id, "error": { "code": code, "message": message } })
}

fn pretty(v: &Value) -> String {
    serde_json::to_string_pretty(v).unwrap_or_else(|_| v.to_string())
}

// ── Tool schemas ─────────────────────────────────────────────────────────────

fn tool(name: &str, description: &str, properties: Value, required: &[&str]) -> Value {
    json!({
        "name": name,
        "description": description,
        "inputSchema": { "type": "object", "properties": properties, "required": required },
    })
}

pub fn tool_list() -> Vec<Value> {
    let pid = json!({ "type": "integer", "minimum": 0, "description": "Prozess-ID (aus find)" });
    let addr = json!({ "type": "string", "description": "Adresse, 0x-hex oder dezimal" });
    let num = |d: &str| json!({ "type": "string", "description": d });
    vec![
        tool(
            "health",
            "BlueStacks-Prozess und adb-Device-Status prüfen; liefert einen Hinweis, was zu tun ist.",
            json!({}),
            &[],
        ),
        tool(
            "find",
            "Spielprozess auf dem Device finden (spectre find --adb).",
            json!({
            "process": { "type": "string", "description": "Teilstring des Prozessnamens" } }),
            &["process"],
        ),
        tool(
            "regions",
            "Speicherregionen eines Prozesses (spectre regions --adb --json).",
            json!({
            "pid": pid,
            "rw_only": { "type": "boolean", "default": true, "description": "nur rw-Regionen" },
            "min_size_bytes": { "type": "integer", "minimum": 0, "default": 0 } }),
            &["pid"],
        ),
        tool(
            "dump",
            "Speicher roh in eine Datei schreiben (spectre dump --format raw).",
            json!({
            "pid": pid, "addr": addr,
            "size": { "type": "integer", "minimum": 1 },
            "out": { "type": "string", "description": "Zieldatei" } }),
            &["pid", "addr", "size", "out"],
        ),
        tool(
            "dumpdiff",
            "Zwei Roh-Dumps vergleichen (spectre dumpdiff --json).",
            json!({
            "a": { "type": "string", "description": "ältere Dump-Datei" },
            "b": { "type": "string", "description": "neuere Dump-Datei" },
            "base": num("virtuelle Adresse des ersten Bytes (Default 0)") }),
            &["a", "b"],
        ),
        tool(
            "read",
            "Einen Wert lesen (kleiner Dump + little-endian Parse).",
            json!({
            "pid": pid, "addr": addr,
            "type": { "type": "string", "enum": ["u8", "u16", "u32", "u64", "i32", "f32", "f64"] } }),
            &["pid", "addr", "type"],
        ),
        tool(
            "hot",
            "Byte-Muster auf dem Device suchen (spectre hot --adb --json).",
            json!({
            "pid": pid,
            "hex": { "type": "string", "description": "Bytes in Speicherreihenfolge, z.B. b8f30300" },
            "base": num("nur Treffer ab dieser Adresse"),
            "limit": { "type": "integer", "minimum": 0 } }),
            &["pid", "hex"],
        ),
        tool(
            "hunt",
            "Kandidaten-Adressen für einen Wertebereich finden (spectre hunt --adb).",
            json!({
            "pid": pid, "min": num("untere Grenze (dezimal oder 0x)"), "max": num("obere Grenze"),
            "type": { "type": "string", "enum": ["u32", "u64", "f32", "f64"], "default": "u32" } }),
            &["pid", "min", "max"],
        ),
        tool(
            "search",
            "Speicher nach einem Wert (value) oder Bereich (min+max) durchsuchen (spectre search --adb).",
            json!({
            "pid": pid,
            "type": { "type": "string", "enum": ["u8", "u16", "u32", "u64", "i8", "i16", "i32", "i64", "f32", "f64"] },
            "value": num("exakter Wert"), "min": num("Bereich: untere Grenze"), "max": num("Bereich: obere Grenze") }),
            &["pid", "type"],
        ),
        tool(
            "chain",
            "Pointer-Chain auflösen (spectre chain --adb --json).",
            json!({
            "pid": pid, "base": addr,
            "offsets": { "type": "string", "description": "kommagetrennt, z.B. 0x10,0x8; leer = rohe Pointer folgen" } }),
            &["pid", "base"],
        ),
        tool(
            "offsets",
            "Offsets-YAML eines Spiels anzeigen + validieren; ohne game: Spiele auflisten.",
            json!({
            "game": { "type": "string" } }),
            &[],
        ),
        tool(
            "adb_tap",
            "Tippen auf dem Device (adb shell input tap).",
            json!({
            "x": { "type": "integer", "minimum": 0 }, "y": { "type": "integer", "minimum": 0 } }),
            &["x", "y"],
        ),
        tool(
            "adb_key",
            "Taste senden (adb shell input keyevent), z.B. back, home, KEYCODE_ENTER, 4.",
            json!({
            "name": { "type": "string" } }),
            &["name"],
        ),
        tool(
            "adb_screencap",
            "Screenshot als PNG speichern (adb exec-out screencap -p).",
            json!({
            "out_png": { "type": "string" } }),
            &["out_png"],
        ),
    ]
}

// ── Tool implementations ─────────────────────────────────────────────────────

struct Ctx<'a, R> {
    cfg: &'a Config,
    r: &'a mut R,
}

impl<R: CommandRunner> Ctx<'_, R> {
    fn run(&mut self, program: &str, args: &[String]) -> Result<Output, String> {
        let timeout = self.cfg.timeout;
        self.r.run(program, args, timeout).map_err(|e| match e {
            RunError::Timeout => format!(
                "Zeitüberschreitung nach {}s bei `{} {}`: CMD_TIMEOUT_SECONDS erhöhen oder mit health prüfen, ob das Device hängt",
                timeout.as_secs(),
                program,
                args.join(" ")
            ),
            RunError::Spawn(e) if program == self.cfg.adb_bin => {
                format!("adb nicht startbar ({program}): {e} — ADB_BIN auf adb.exe setzen")
            }
            RunError::Spawn(e) => format!(
                "spectre nicht startbar ({program}): {e} — `cargo build --release -p spectre-cli` ausführen oder SPECTRE_BIN setzen"
            ),
        })
    }

    /// adb against the configured device; non-zero exit is an error.
    fn adb(&mut self, args: &[&str]) -> Result<Output, String> {
        let mut full = vec!["-s".to_owned(), self.cfg.serial.clone()];
        full.extend(args.iter().map(|s| s.to_string()));
        let adb = self.cfg.adb_bin.clone();
        let out = self.run(&adb, &full)?;
        if out.success() {
            return Ok(out);
        }
        let detail = String::from_utf8_lossy(&out.stderr).trim().to_owned();
        Err(format!(
            "`adb {}` fehlgeschlagen (exit {:?}): {detail}{}",
            args.join(" "),
            out.code,
            DEVICE_HINT
        ))
    }

    fn reconnect(&mut self) {
        let adb = self.cfg.adb_bin.clone();
        let args = vec!["connect".to_owned(), self.cfg.serial.clone()];
        if let Err(e) = self.run(&adb, &args) {
            eprintln!("spectre-mcp: adb connect: {e}");
        }
    }

    /// Run spectre, then re-attach adb; returns stdout.
    fn spectre(&mut self, args: Vec<String>) -> Result<String, String> {
        let bin = self.cfg.spectre_bin.clone();
        let result = self.run(&bin, &args);
        self.reconnect();
        let out = result?;
        let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
        if out.success() {
            return Ok(stdout);
        }
        let stderr = String::from_utf8_lossy(&out.stderr);
        let detail = tail(&format!("{}\n{}", stderr.trim(), stdout.trim()), 1500);
        let hint = if needs_device(&detail) {
            DEVICE_HINT
        } else {
            ""
        };
        Err(format!(
            "`spectre {}` fehlgeschlagen (exit {:?}): {detail}{hint}",
            args.first().map(String::as_str).unwrap_or_default(),
            out.code
        ))
    }

    fn adb_flags(&self) -> Vec<String> {
        let (host, port) = self.cfg.host_port();
        strings(&["--adb", "--adb-host", host, "--adb-port", port])
    }

    fn tool(&mut self, name: &str, a: &Value) -> Result<Value, String> {
        match name {
            "health" => self.health(),
            "find" => {
                let process = text(a, "process")?;
                let out = self.spectre(strings(&["find", &process, "--adb", "--json"]))?;
                let list: Value = serde_json::from_str(&out).map_err(|_| {
                    format!("Prozess '{process}' nicht gefunden: Spiel in BlueStacks öffnen, dann find erneut ({})", out.trim())
                })?;
                let pid = list
                    .get(0)
                    .and_then(|p| p.get("pid"))
                    .cloned()
                    .unwrap_or(Value::Null);
                Ok(json!({ "pid": pid, "processes": list }))
            }
            "regions" => {
                let pid = int(a, "pid")?;
                let rw_only = a.get("rw_only").and_then(Value::as_bool).unwrap_or(true);
                let min = opt_int(a, "min_size_bytes")?.unwrap_or(0);
                let mut args = strings(&["regions", &pid.to_string(), "--adb", "--json"]);
                if rw_only {
                    args.extend(strings(&["--filter", "rw"]));
                }
                let out = self.spectre(args)?;
                let all: Vec<Value> = serde_json::from_str(&out)
                    .map_err(|e| format!("regions-Ausgabe kein JSON ({e}): {}", tail(&out, 500)))?;
                let regions: Vec<Value> = all
                    .into_iter()
                    .filter(|r| r["size"].as_u64().unwrap_or(0) >= min)
                    .collect();
                Ok(json!({ "count": regions.len(), "regions": regions }))
            }
            "dump" => {
                let (pid, addr, size, out) = (
                    int(a, "pid")?,
                    text(a, "addr")?,
                    int(a, "size")?,
                    text(a, "out")?,
                );
                let bytes = self.dump(pid, &addr, size, &out)?;
                Ok(json!({ "path": out, "size": bytes.len(), "sha1": sha1_hex(&bytes) }))
            }
            "dumpdiff" => {
                let base = opt_text(a, "base").unwrap_or_else(|| "0".to_owned());
                let out = self.spectre(strings(&[
                    "dumpdiff",
                    &text(a, "a")?,
                    &text(a, "b")?,
                    "--base",
                    &base,
                    "--json",
                ]))?;
                Ok(json_or_text(out))
            }
            "read" => self.read(a),
            "hot" => {
                let mut args = strings(&["hot", &int(a, "pid")?.to_string(), &text(a, "hex")?]);
                args.extend(self.adb_flags());
                args.push("--json".to_owned());
                if let Some(base) = opt_text(a, "base") {
                    args.extend(["--base".to_owned(), base]);
                }
                if let Some(limit) = opt_int(a, "limit")? {
                    args.extend(["--limit".to_owned(), limit.to_string()]);
                }
                Ok(json_or_text(self.spectre(args)?))
            }
            "hunt" => {
                let vtype = opt_text(a, "type").unwrap_or_else(|| "u32".to_owned());
                let mut args = strings(&[
                    "hunt",
                    &int(a, "pid")?.to_string(),
                    &text(a, "min")?,
                    &text(a, "max")?,
                ]);
                args.extend(self.adb_flags());
                args.extend(["--type".to_owned(), vtype]);
                Ok(json!({ "output": self.spectre(args)? }))
            }
            "search" => {
                let mut args = strings(&["search", &int(a, "pid")?.to_string(), &text(a, "type")?]);
                match (opt_text(a, "value"), opt_text(a, "min"), opt_text(a, "max")) {
                    (Some(v), None, None) => args.push(v),
                    (None, Some(min), Some(max)) => {
                        args.extend(["--min".to_owned(), min, "--max".to_owned(), max])
                    }
                    _ => return Err("search braucht entweder value oder min+max".to_owned()),
                }
                // shortcut: search/dump/find/regions/chain take only --adb (CLI uses 127.0.0.1:5555); add host/port once the CLI has the flags.
                args.push("--adb".to_owned());
                Ok(json!({ "output": self.spectre(args)? }))
            }
            "chain" => {
                let pid = int(a, "pid")?.to_string();
                let mut args =
                    strings(&["chain", &text(a, "base")?, "--pid", &pid, "--adb", "--json"]);
                if let Some(offsets) = opt_text(a, "offsets").filter(|o| !o.trim().is_empty()) {
                    args.extend(["--offsets".to_owned(), offsets]);
                }
                Ok(json_or_text(self.spectre(args)?))
            }
            "offsets" => {
                let mut args = vec!["offsets".to_owned()];
                args.extend(opt_text(a, "game"));
                args.push("--json".to_owned());
                Ok(json_or_text(self.spectre(args)?))
            }
            "adb_tap" => {
                let (x, y) = (int(a, "x")?.to_string(), int(a, "y")?.to_string());
                self.adb(&["shell", "input", "tap", &x, &y])?;
                Ok(json!({ "ok": true, "x": x, "y": y }))
            }
            "adb_key" => {
                let code = keycode(&text(a, "name")?)?;
                self.adb(&["shell", "input", "keyevent", &code])?;
                Ok(json!({ "ok": true, "key": code }))
            }
            "adb_screencap" => {
                let path = text(a, "out_png")?;
                let png = self.adb(&["exec-out", "screencap", "-p"])?.stdout;
                if !png.starts_with(b"\x89PNG") {
                    return Err(format!(
                        "screencap lieferte kein PNG ({} Bytes){DEVICE_HINT}",
                        png.len()
                    ));
                }
                std::fs::write(&path, &png).map_err(|e| format!("{path} nicht schreibbar: {e}"))?;
                Ok(json!({ "path": path, "size": png.len() }))
            }
            other => Err(format!("unbekanntes Tool: {other}")),
        }
    }

    fn health(&mut self) -> Result<Value, String> {
        let probe = if cfg!(windows) {
            (
                "tasklist",
                strings(&["/FI", "IMAGENAME eq HD-Player.exe", "/NH"]),
            )
        } else {
            ("pgrep", strings(&["-f", "HD-Player"]))
        };
        let bluestacks = self
            .run(probe.0, &probe.1)
            // tasklist exits 0 even without a match, so Windows checks the text.
            .map(|o| {
                if cfg!(windows) {
                    String::from_utf8_lossy(&o.stdout).contains("HD-Player")
                } else {
                    o.success()
                }
            })
            .unwrap_or(false);
        self.reconnect();
        let (adb_state, adb_missing) = match self.adb(&["get-state"]) {
            Ok(o) => (String::from_utf8_lossy(&o.stdout).trim().to_owned(), false),
            Err(e) => (
                if e.contains("nicht startbar") {
                    "adb fehlt"
                } else {
                    "kein device"
                }
                .to_owned(),
                e.contains("nicht startbar"),
            ),
        };
        let hint = if adb_missing {
            "adb nicht gefunden: ADB_BIN auf adb.exe setzen".to_owned()
        } else if !bluestacks {
            "BlueStacks läuft nicht: scripts/bluestacks-ensure.sh starten".to_owned()
        } else if adb_state != "device" {
            format!(
                "kein Device unter {}: scripts/bluestacks-ensure.sh starten",
                self.cfg.serial
            )
        } else {
            "ok".to_owned()
        };
        Ok(json!({ "bluestacks_running": bluestacks, "adb_state": adb_state, "hint": hint }))
    }

    fn dump(&mut self, pid: u64, addr: &str, size: u64, out: &str) -> Result<Vec<u8>, String> {
        self.spectre(strings(&[
            "dump",
            &pid.to_string(),
            addr,
            &size.to_string(),
            "--adb",
            "--format",
            "raw",
            "--output",
            out,
        ]))?;
        std::fs::read(out).map_err(|e| format!("Dump-Datei {out} nicht lesbar: {e}"))
    }

    fn read(&mut self, a: &Value) -> Result<Value, String> {
        let (pid, addr, vtype) = (int(a, "pid")?, text(a, "addr")?, text(a, "type")?);
        let size = match vtype.as_str() {
            "u8" => 1,
            "u16" => 2,
            "u32" | "i32" | "f32" => 4,
            "u64" | "f64" => 8,
            other => {
                return Err(format!(
                    "Typ '{other}' unbekannt: u8|u16|u32|u64|i32|f32|f64"
                ));
            }
        };
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or_default();
        let tmp = std::env::temp_dir().join(format!(
            "spectre-mcp-read-{}-{nanos}.bin",
            std::process::id()
        ));
        let tmp_str = tmp.to_string_lossy().into_owned();
        let bytes = self.dump(pid, &addr, size as u64, &tmp_str);
        let _ = std::fs::remove_file(&tmp);
        let b = bytes?;
        if b.len() < size {
            return Err(format!(
                "nur {} von {size} Bytes gelesen bei {addr}: Adresse prüfen (regions)",
                b.len()
            ));
        }
        let mut w = [0u8; 8];
        w[..size].copy_from_slice(&b[..size]);
        let raw = u64::from_le_bytes(w);
        let value = match vtype.as_str() {
            "i32" => json!(raw as u32 as i32),
            "f32" => json!(f32::from_bits(raw as u32) as f64),
            "f64" => json!(f64::from_bits(raw)),
            _ => json!(raw),
        };
        Ok(json!({ "addr": addr, "type": vtype, "value": value }))
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

fn strings(items: &[&str]) -> Vec<String> {
    items.iter().map(|s| s.to_string()).collect()
}

fn tail(s: &str, max: usize) -> String {
    let s = s.trim();
    match s.char_indices().rev().nth(max) {
        Some((i, _)) => format!("…{}", &s[i..]),
        None => s.to_owned(),
    }
}

fn needs_device(text: &str) -> bool {
    let t = text.to_ascii_lowercase();
    [
        "no devices",
        "device offline",
        "device not found",
        "unauthorized",
        "cannot connect",
        "failed to connect",
        "not found: 127.",
    ]
    .iter()
    .any(|p| t.contains(p))
}

fn json_or_text(out: String) -> Value {
    serde_json::from_str(&out).unwrap_or(json!({ "output": out }))
}

fn opt_text(a: &Value, key: &str) -> Option<String> {
    match a.get(key)? {
        Value::String(s) if !s.is_empty() => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

fn text(a: &Value, key: &str) -> Result<String, String> {
    opt_text(a, key).ok_or_else(|| format!("Argument '{key}' fehlt oder ist leer"))
}

fn opt_int(a: &Value, key: &str) -> Result<Option<u64>, String> {
    let Some(v) = a.get(key).filter(|v| !v.is_null()) else {
        return Ok(None);
    };
    let parsed = match v {
        Value::Number(n) => n.as_u64(),
        Value::String(s) => match s.strip_prefix("0x") {
            Some(hex) => u64::from_str_radix(hex, 16).ok(),
            None => s.parse().ok(),
        },
        _ => None,
    };
    parsed.map(Some).ok_or_else(|| {
        format!("Argument '{key}' muss eine nicht-negative Ganzzahl sein, nicht {v}")
    })
}

fn int(a: &Value, key: &str) -> Result<u64, String> {
    opt_int(a, key)?.ok_or_else(|| format!("Argument '{key}' fehlt"))
}

/// Key name -> Android keycode; validated because it ends up in `adb shell`.
fn keycode(name: &str) -> Result<String, String> {
    let n = name.trim().to_ascii_uppercase();
    if n.is_empty() || !n.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
        return Err(format!(
            "Tastenname '{name}' ungültig: nur A-Z, 0-9, _ (z.B. back, KEYCODE_HOME, 4)"
        ));
    }
    if n.starts_with("KEYCODE_") || n.chars().all(|c| c.is_ascii_digit()) {
        Ok(n)
    } else {
        Ok(format!("KEYCODE_{n}"))
    }
}

/// SHA-1 (FIPS 180-1) hex digest; only used to fingerprint dump files.
pub fn sha1_hex(data: &[u8]) -> String {
    let mut h: [u32; 5] = [
        0x6745_2301,
        0xEFCD_AB89,
        0x98BA_DCFE,
        0x1032_5476,
        0xC3D2_E1F0,
    ];
    let mut msg = data.to_vec();
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&((data.len() as u64).wrapping_mul(8)).to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 80];
        for (word, bytes) in w.iter_mut().zip(chunk.chunks(4)) {
            *word = u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]);
        }
        for i in 16..80 {
            w[i] = (w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]).rotate_left(1);
        }
        let [mut a, mut b, mut c, mut d, mut e] = h;
        for (i, wi) in w.iter().enumerate() {
            let (f, k) = match i {
                0..=19 => ((b & c) | (!b & d), 0x5A82_7999),
                20..=39 => (b ^ c ^ d, 0x6ED9_EBA1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8F1B_BCDC),
                _ => (b ^ c ^ d, 0xCA62_C1D6),
            };
            let t = a
                .rotate_left(5)
                .wrapping_add(f)
                .wrapping_add(e)
                .wrapping_add(k)
                .wrapping_add(*wi);
            (e, d, c, b, a) = (d, c, b.rotate_left(30), a, t);
        }
        for (x, y) in h.iter_mut().zip([a, b, c, d, e]) {
            *x = x.wrapping_add(y);
        }
    }
    h.iter().map(|x| format!("{x:08x}")).collect()
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    type Respond = fn(&str, &[String]) -> Result<Output, RunError>;

    struct Fake {
        calls: Vec<(String, Vec<String>)>,
        respond: Respond,
    }

    impl CommandRunner for Fake {
        fn run(&mut self, program: &str, args: &[String], _: Duration) -> Result<Output, RunError> {
            self.calls.push((program.to_owned(), args.to_vec()));
            (self.respond)(program, args)
        }
    }

    fn ok(stdout: &str) -> Result<Output, RunError> {
        Ok(Output {
            code: Some(0),
            stdout: stdout.as_bytes().to_vec(),
            stderr: vec![],
        })
    }

    fn server(respond: Respond) -> Server<Fake> {
        let config = Config {
            spectre_bin: "spectre".into(),
            adb_bin: "adb".into(),
            serial: "127.0.0.1:5555".into(),
            timeout: Duration::from_secs(5),
        };
        Server::new(
            config,
            Fake {
                calls: vec![],
                respond,
            },
        )
    }

    fn call(s: &Server<Fake>, name: &str, args: Value) -> Value {
        let req = json!({ "jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": { "name": name, "arguments": args } });
        s.handle(&req).expect("response")
    }

    fn calls(s: &Server<Fake>) -> Vec<(String, Vec<String>)> {
        s.runner.lock().unwrap().calls.clone()
    }

    fn text_of(resp: &Value) -> &str {
        resp["result"]["content"][0]["text"].as_str().unwrap()
    }

    #[test]
    fn initialize_echoes_client_version_and_notifications_are_silent() {
        let s = server(|_, _| ok(""));
        let resp = s.handle_line(r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2099-01-01","capabilities":{}}}"#).unwrap();
        let v: Value = serde_json::from_str(&resp).unwrap();
        assert_eq!(v["id"], 1);
        assert_eq!(v["result"]["protocolVersion"], "2099-01-01");
        assert!(v["result"]["capabilities"]["tools"].is_object());
        assert!(
            s.handle_line(r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#)
                .is_none()
        );
        let bad: Value = serde_json::from_str(&s.handle_line("{nope").unwrap()).unwrap();
        assert_eq!(bad["error"]["code"], -32700);
    }

    #[test]
    fn tools_list_schemas_are_valid() {
        let s = server(|_, _| ok(""));
        let v = s
            .handle(&json!({ "jsonrpc": "2.0", "id": 2, "method": "tools/list" }))
            .unwrap();
        let tools = v["result"]["tools"].as_array().unwrap();
        assert_eq!(tools.len(), 14);
        let mut names: Vec<&str> = tools.iter().map(|t| t["name"].as_str().unwrap()).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), 14);
        for t in tools {
            assert!(!t["description"].as_str().unwrap().is_empty());
            let schema = &t["inputSchema"];
            assert_eq!(schema["type"], "object");
            for req in schema["required"].as_array().unwrap() {
                assert!(
                    schema["properties"].get(req.as_str().unwrap()).is_some(),
                    "{} requires missing {req}",
                    t["name"]
                );
            }
        }
    }

    #[test]
    fn find_success_maps_args_and_reconnects() {
        let s = server(|p, _| {
            if p == "spectre" {
                ok(r#"[{"pid":4321,"name":"com.game"}]"#)
            } else {
                ok("")
            }
        });
        let resp = call(&s, "find", json!({ "process": "game" }));
        assert_eq!(resp["result"]["isError"], false);
        let body: Value = serde_json::from_str(text_of(&resp)).unwrap();
        assert_eq!(body["pid"], 4321);
        assert_eq!(
            calls(&s),
            vec![
                (
                    "spectre".to_owned(),
                    strings(&["find", "game", "--adb", "--json"])
                ),
                ("adb".to_owned(), strings(&["connect", "127.0.0.1:5555"])),
            ]
        );
    }

    #[test]
    fn spectre_failure_is_tool_error_with_device_hint() {
        let s = server(|p, _| {
            if p == "spectre" {
                Ok(Output {
                    code: Some(1),
                    stdout: vec![],
                    stderr: b"Error: adb: no devices/emulators found".to_vec(),
                })
            } else {
                ok("")
            }
        });
        let resp = call(&s, "regions", json!({ "pid": 1 }));
        assert_eq!(resp["result"]["isError"], true);
        assert!(
            text_of(&resp).contains("bluestacks-ensure.sh"),
            "{}",
            text_of(&resp)
        );
        // adb connect still runs after the failed spectre command
        assert_eq!(calls(&s).last().unwrap().1[0], "connect");
    }

    #[test]
    fn unknown_tool_and_missing_args() {
        let s = server(|_, _| ok(""));
        let resp = call(&s, "nope", json!({}));
        assert_eq!(resp["error"]["code"], -32602);
        let resp = call(&s, "dump", json!({ "pid": 1 }));
        assert_eq!(resp["result"]["isError"], true);
        assert!(text_of(&resp).contains("'addr' fehlt"));
        assert!(calls(&s).is_empty());
    }

    #[test]
    fn timeout_is_tool_error() {
        let s = server(|_, _| Err(RunError::Timeout));
        let resp = call(&s, "hunt", json!({ "pid": 1, "min": "10", "max": "20" }));
        assert_eq!(resp["result"]["isError"], true);
        assert!(text_of(&resp).contains("Zeitüberschreitung"));
    }

    #[test]
    fn system_runner_kills_on_timeout() {
        let (prog, args) = if cfg!(windows) {
            ("ping", strings(&["-n", "10", "127.0.0.1"]))
        } else {
            ("sleep", strings(&["10"]))
        };
        let start = Instant::now();
        let r = SystemRunner.run(prog, &args, Duration::from_millis(300));
        assert_eq!(r.unwrap_err(), RunError::Timeout);
        assert!(start.elapsed() < Duration::from_secs(5));
    }

    #[test]
    fn adb_tap_and_key_command_lines() {
        let s = server(|_, _| ok(""));
        assert_eq!(
            call(&s, "adb_tap", json!({ "x": 100, "y": 200 }))["result"]["isError"],
            false
        );
        assert_eq!(
            call(&s, "adb_key", json!({ "name": "back" }))["result"]["isError"],
            false
        );
        assert_eq!(
            call(&s, "adb_key", json!({ "name": "a;reboot" }))["result"]["isError"],
            true
        );
        assert_eq!(
            calls(&s),
            vec![
                (
                    "adb".to_owned(),
                    strings(&[
                        "-s",
                        "127.0.0.1:5555",
                        "shell",
                        "input",
                        "tap",
                        "100",
                        "200"
                    ])
                ),
                (
                    "adb".to_owned(),
                    strings(&[
                        "-s",
                        "127.0.0.1:5555",
                        "shell",
                        "input",
                        "keyevent",
                        "KEYCODE_BACK"
                    ])
                ),
            ]
        );
    }

    #[test]
    fn hot_passes_host_port_and_options() {
        let s = server(|_, _| ok(r#"["0x7000"]"#));
        let resp = call(
            &s,
            "hot",
            json!({ "pid": 9, "hex": "b8f30300", "base": "0x70000000", "limit": 5 }),
        );
        assert_eq!(resp["result"]["isError"], false);
        assert_eq!(
            calls(&s)[0].1,
            strings(&[
                "hot",
                "9",
                "b8f30300",
                "--adb",
                "--adb-host",
                "127.0.0.1",
                "--adb-port",
                "5555",
                "--json",
                "--base",
                "0x70000000",
                "--limit",
                "5"
            ])
        );
    }

    #[test]
    fn read_parses_little_endian_and_cleans_up() {
        let s = server(|p, args| {
            if p == "spectre" {
                let out = &args[args.iter().position(|a| a == "--output").unwrap() + 1];
                std::fs::write(out, 259_000u32.to_le_bytes()).unwrap();
            }
            ok("")
        });
        let resp = call(
            &s,
            "read",
            json!({ "pid": 3, "addr": "0x10", "type": "u32" }),
        );
        let body: Value = serde_json::from_str(text_of(&resp)).unwrap();
        assert_eq!(body["value"], 259_000);
        let args = &calls(&s)[0].1;
        assert_eq!(
            &args[..5],
            &strings(&["dump", "3", "0x10", "4", "--adb"])[..]
        );
        assert!(!std::path::Path::new(&args[args.len() - 1]).exists());
    }

    #[test]
    fn sha1_known_vectors() {
        assert_eq!(sha1_hex(b"abc"), "a9993e364706816aba3e25717850c26c9cd0d89d");
        assert_eq!(sha1_hex(b""), "da39a3ee5e6b4b0d3255bfef95601890afd80709");
        let long = b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
        assert_eq!(sha1_hex(long), "84983e441c3bd26ebaae4aa1f95129e5e54670f1");
    }
}
