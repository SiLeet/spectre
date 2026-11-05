# H<n> — <Wert> (<Datum>)

- **PID / BASE:** <pid> / <0x…> (aus `.spectre/power-state.json`, Zeitstempel)
- **Auslöser:** <Aktion, ohne Diamanten>
- **Bildschirm:** vorher <v0> → nachher <v1> (wie abgelesen; Screenshot-Pfad)
- **Typen gesucht:** u32 / i64 / f64 / Dump-Diff-Slot-Modus

## Gelaufene Befehle

```
<exakt wie ausgeführt, je Zeile mit Uhrzeit>
```

## Kandidaten je Durchgang

| Durchgang | Typ | Kandidaten |
|---|---|---|
| 1 (v0) | u32 | |
| 2 (--continue v1) | u32 | |
| 3 (Stabilität, 60 s) | u32 | |
| Dump-Diff `--from v0 --to v1` | u32 | <Summe über alle Heaps> |

## Überlebende

| Adresse | Typ | Region (start, size, perms) | Offset in der Region | Offset zu BASE | Abstand zum team_power-Slot | Kontext (96 B ab Adresse−32, hex) |
|---|---|---|---|---|---|---|

## Rohdateien

`%TEMP%/spectre-hunt/h<n>_…` (Liste)

## Neustart-Check

offen | erledigt am <Datum>: neuer PID <…>, Abstand gleich ja/nein, Wert getroffen ja/nein
