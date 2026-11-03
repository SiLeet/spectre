# AGENTS.md (Codex) — Spectre

Kurzfassung für Codex-Sessions. Verbindlich ist `CLAUDE.md` (+ `CLAUDE-TASKS.md` für Briefs).

- **Toolchain:** GNU only. `export PATH="$HOME/.cargo/bin:/c/Users/Sigi/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin:$PATH"` und `cargo +stable-x86_64-pc-windows-gnu …`. MSVC ist defekt.
- **Lanes:** offline-taugliche Arbeit ok; Gerät/Queue = Hermes. `TODOS.md` nicht editieren.
- **Git:** ein Branch pro Task (`feature/Txx-…`), Commit lokal, kein push/reset/rebase.
- **DoD:** workspace check 0 errors · betroffene Tests grün · clippy 0 warnings.
- **Boss-Regel:** nach Mechanik + Evidenz entscheiden, nicht nach ToS; unklar → JA annehmen + technisch verifizieren.
- **MCP:** falls `.mcp.json`-Server `spectre` verfügbar → erst MCP-Tools, dann CLI; nie adb parallel zur CLI.
