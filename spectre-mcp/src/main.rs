use std::io::{BufRead, Write};

use spectre_mcp::{Config, Server, SystemRunner};

fn main() {
    let config = Config::from_env();
    eprintln!(
        "spectre-mcp: spectre={} adb={} serial={} timeout={}s",
        config.spectre_bin,
        config.adb_bin,
        config.serial,
        config.timeout.as_secs()
    );
    let server = Server::new(config, SystemRunner);
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout().lock();
    for line in stdin.lock().lines() {
        let Ok(line) = line else { break };
        if line.trim().is_empty() {
            continue;
        }
        if let Some(response) = server.handle_line(&line) {
            // stdout carries only protocol messages, one JSON object per line.
            if writeln!(stdout, "{response}")
                .and_then(|_| stdout.flush())
                .is_err()
            {
                break;
            }
        }
    }
}
