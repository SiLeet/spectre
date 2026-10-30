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

**a. Memory scanning with known values:**
- Set your character level to a known value (e.g. 42)
- Search for the u32 value `42` in process memory
- Narrow down by checking nearby values

**b. Pointer chain traversal:**
- Find a global pointer in the game's binary
- Use `spectre dump` to explore memory from that pointer
- Map out the structure fields

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