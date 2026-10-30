# AFK Journey — Memory Offsets

> Game version tested: 1.0.45

## Structures

This offset file maps the following structures in AFK Journey (AFK Journey) process memory.

### PlayerState
Base offset for player identity and progression data.

| Offset | Field        | Type     | Description             |
|--------|--------------|----------|-------------------------|
| 0x00   | player_id    | U32      | Account ID              |
| 0x04   | level        | U32      | Player level            |
| 0x08   | exp          | U64      | Current EXP             |
| 0x10   | nickname     | String(32) | Player display name   |
| 0x30   | vip_level    | U32      | VIP / battle pass tier  |
| 0x34   | create_time  | U64      | Account creation (unix)  |

### Resources
In-game currencies and materials.

| Offset | Field        | Type     | Description             |
|--------|--------------|----------|-------------------------|
| 0x00   | gold         | I64      | Gold coins              |
| 0x08   | gems         | I64      | Premium gems            |
| 0x10   | energy       | U32      | Stamina                 |
| 0x14   | arena_tokens | U32      | Arena currency          |
| 0x18   | guild_tokens | U32      | Guild currency          |

### TeamState
Current hero deployment.

| Offset | Field         | Type       | Description           |
|--------|---------------|------------|-----------------------|
| 0x00   | hero_count    | U32        | Deployed heroes       |
| 0x04   | team_power    | U64        | Combat power          |
| 0x0C   | formation_id  | U32        | Formation slot        |
| 0x10   | heroes_ptr    | Pointer64  | Hero array pointer    |

### HeroInfo
Individual hero data (dereferenced from heroes_ptr).

| Offset | Field         | Type       | Description           |
|--------|---------------|------------|-----------------------|
| 0x00   | hero_id       | U32        | Hero template ID      |
| 0x04   | level         | U32        | Hero level            |
| 0x08   | ascension     | U32        | Ascension tier        |
| 0x0C   | power         | U64        | Hero combat power     |
| 0x14   | stars         | U32        | Star count            |
| 0x18   | gear_ptr      | Pointer64  | Equipment pointer     |
| 0x20   | skills_ptr    | Pointer64  | Skill data pointer    |

## Discovery Notes

These offsets were found using the gold-spend diff method:
1. Player gold was recorded before and after a purchase
2. The changed u64 was the gold field
3. Nearby values were cross-referenced with known in-game values

## Version Compatibility

| Game Version  | Offsets Verified |
|---------------|------------------|
| 1.0.45        | ✅ Verified      |
| 1.0.44        | ✅ Likely compatible |
| < 1.0.44      | ❌ May not work  |

## Usage

```bash
spectre scan afk-journey
```