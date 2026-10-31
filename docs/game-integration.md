# Game Integration Guide

This guide explains how to add support for a new game to Spectre.

## Overview

Adding a new game requires one thing: an offset YAML file. No Rust code needed.
The offset file maps known data structures in the game's process memory so that
Spectre's scanner can find and read them.

## Step-by-Step

### 1. Create the game directory

```bash
mkdir -p games/my-game
```

### 2. Write offsets.yaml

Create `games/my-game/offsets.yaml`:

```yaml
game: "my-game"
version: "1.2.3"
structures:
  - name: "PlayerState"
    base_offset: 0x12345678
    fields:
      - name: "player_id"
        field_type: U32
        offset: 0x00
        desc: "Unique player identifier"

  - name: "Resources"
    base_offset: 0x23456789
    fields:
      - name: "gold"
        field_type: I64
        offset: 0x00
        desc: "Current gold amount"
      - name: "gems"
        field_type: I64
        offset: 0x08
        desc: "Premium currency"
      - name: "energy"
        field_type: U32
        offset: 0x10
        desc: "Stamina/energy"
```

### 3. Discover offsets

Finding offsets is the hard part. Common approaches:

**a. Memory scanning with known values (Spectre `search`):**
- Set your character level to a known value (e.g. 42)
- Find the game's PID: `spectre find my-game`
- Search for the value in process memory:
  ```bash
  spectre search <pid> u32 42 --limit 100
  ```
  Results are saved to `.spectre-search.json` by default.
- Perform an action that changes the value (level up, spend gold, ...)
- Refine the candidate list with the new value — this drops stale addresses
  and converges on the real location:
  ```bash
  spectre search <pid> u32 55 --continue
  ```
- Repeat until one address remains, then note its offset relative to a
  stable base (pointer chain).

**b. Pointer chain traversal:**
- Find a global pointer in the game's binary
- Use `spectre dump` to explore memory from that pointer
- Map out the structure fields

`spectre chain` does the dereferencing for you. Without offsets it follows
raw pointers from an address and tells you where and why the chain ends
(NULL, a cycle, unreadable memory, or `--depth`):

```bash
spectre chain 0x7ff0000 --pid <pid> --depth 8
```

Once you know the offsets, resolve the full path. Each offset is added before
its dereference, the start address itself is *not* dereferenced, and the last
offset gives the final field address (`[[0x7ff0000+0x10]+0x8]+0x30`):

```bash
spectre chain 0x7ff0000 --pid <pid> --offsets 0x10,0x8,0x30
```

Cheat Engine pointer paths dereference the base first (`[[base]+o0]+o1`), so
copy a CE path `base -> [o0, o1, ..]` with a leading `0` offset:

```bash
spectre chain <base> --pid <pid> --offsets 0,<o0>,<o1>
```

Re-run it after restarting the game: if `resolved` still points at the value
you found with `search`, the chain is stable enough for `offsets.yaml`. See
[`chain` in the CLI reference](cli-reference.md#chain) for the output format.

**c. Diff-based discovery:**
- Dump memory before and after an action (e.g. gaining gold)
- Diff the dumps to identify changed bytes
- Correlate known values to field types

**d. Reverse engineering the binary:**
- Use tools like IDA, Ghidra, or Binary Ninja
- Find class fields and their offsets in the game's ELF/PE

### 4. Validate

```bash
spectre scan my-game
```

If the offsets are correct, matches will show plausible values.
Tweak offsets and re-scan until values match expectations.

## Field Types

| Type          | Size  | Description                    |
|---------------|-------|--------------------------------|
| `U8`          | 1     | Unsigned 8-bit integer         |
| `U16`         | 2     | Unsigned 16-bit integer        |
| `U32`         | 4     | Unsigned 32-bit integer        |
| `U64`         | 8     | Unsigned 64-bit integer        |
| `I8`          | 1     | Signed 8-bit integer           |
| `I16`         | 2     | Signed 16-bit integer          |
| `I32`         | 4     | Signed 32-bit integer          |
| `I64`         | 8     | Signed 64-bit integer          |
| `F32`         | 4     | IEEE 754 single-precision float|
| `F64`         | 8     | IEEE 754 double-precision float|
| `Bool`        | 1     | Boolean (0/1)                  |
| `String(N)`   | N     | Null-terminated string of max N bytes |
| `Pointer32`   | 4     | 32-bit memory pointer          |
| `Pointer64`   | 8     | 64-bit memory pointer          |

Spelling rules:

- The type key may be `field_type` (as in the examples here) or `type`.
- Type names are case-insensitive: `U32` and `u32`, `Pointer64` and
  `pointer64` are the same. `ptr32`, `ptr64` and `pointer` are aliases.
- Strings: `String(N)`, `string(N)` or `string:N`; a plain `string` is 128
  bytes. `spectre scan` also accepts a separate `length: N` key on a string
  field (see `examples/practice-offsets.yaml`).
- `spectre scan` rejects an unknown type or a malformed string length
  (`String(abc)`, `String(0)`) with an error naming the structure and field.

## Tips

- **Start simple:** Find one scalar field (level, gold) before complex structures.
- **Alignment:** Most fields align to their size boundary (4-byte u32, 8-byte u64).
- **Endianness:** Mobile games typically use little-endian byte order.
- **ASLR:** Base addresses change every restart. Scan uses relative addressing per region.
- **Updates:** Game patches can shift offsets. Track versions in `version` field.
- **Multiple versions:** You can have multiple offset files or one file with conditional structures.

## Example Structure

```yaml
- name: "TeamState"
  base_offset: 0x34567890
  fields:
    - name: "hero_count"
      field_type: U32
      offset: 0x00
      desc: "Number of deployed heroes"
    - name: "team_power"
      field_type: U64
      offset: 0x04
      desc: "Total team combat power"
    - name: "formation_id"
      field_type: U32
      offset: 0x0C
      desc: "Active formation slot ID"
    - name: "heroes_ptr"
      field_type: Pointer64
      offset: 0x10
      desc: "Pointer to hero array"
```

## Contributing

Once you have working offsets for a game:

1. Create a PR with your `games/<game>/offsets.yaml` file
2. Include a `README.md` noting:
   - Game version tested
   - Discovery method used
   - Any special notes about the structure
3. Run `spectre scan <game>` to confirm output
4. Submit!