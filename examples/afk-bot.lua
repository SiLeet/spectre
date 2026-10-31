-- AFK Journey — AFK bot example for Spectre
-- Two modes, picked with the SPECTRE_MODE environment variable:
--   battle      (default) checks battle status, collects rewards, starts next fight
--   safe_claim  only the zero-risk actions from docs/afk-journey-guide.md:
--               reads gold/EXP and claims login rewards every 5 minutes,
--               logging the gold before/after (a quick offset check)
--
-- Usage:  spectre script examples/afk-bot.lua --input-backend adb
--         $env:SPECTRE_MODE = "safe_claim"; spectre script examples/afk-bot.lua
--         (bash: SPECTRE_MODE=safe_claim spectre script examples/afk-bot.lua)

bot.log("=== AFK Journey Bot Starting ===")

-- ── Configuration ──────────────────────────────────────────────────
local MODE           = os.getenv("SPECTRE_MODE") or "battle"
if MODE ~= "battle" and MODE ~= "safe_claim" then
    error("unknown SPECTRE_MODE '" .. MODE .. "' (use battle or safe_claim)")
end
local TARGET_PROCESS = "afk_journey.exe"
local OFFSET_HP      = 0x12345678   -- Replace with actual offset from spectre-game
local OFFSET_ENERGY  = 0x1234567C
local OFFSET_BATTLE  = 0x12345680   -- 0 = idle, 1 = fighting, 2 = victory

-- Screen coordinates for the target device (adjust per resolution)
local BTN_SKIP      = { x = 1800, y = 60 }
local BTN_RETRY     = { x = 960,  y = 900 }
local BTN_COLLECT   = { x = 960,  y = 980 }
local BTN_START     = { x = 960,  y = 1000 }

local POLL_INTERVAL = 2000   -- ms between checks
local CYCLE_WAIT    = 3000   -- ms between battle cycles

-- safe_claim mode. PLACEHOLDERS: REPLACE both addresses with ones you
-- verified (examples/README.md, "AFK Journey pattern"); until then the
-- reads fail, are logged, and nothing is clicked. Reads are native-only:
-- addresses found with `--adb` inside an emulator do not work here.
local OFFSET_GOLD   = 0xDEADBEEF   -- REPLACE with verified gold address (i64)
local OFFSET_EXP    = 0xCAFEBABE   -- REPLACE with verified EXP address (u64)
local BTN_LOGIN_REWARDS = { x = 1804, y = 662 }   -- Town screen, from the guide
local BTN_CLAIM         = { x = 960,  y = 935 }   -- REPLACE: Journey's Gift Claim (not in the guide)
local CLAIM_INTERVAL    = 300000                  -- ms between claim rounds (5 min)

-- ── Helpers ────────────────────────────────────────────────────────

function hex(v)
    return string.format("0x%X", v)
end

-- Wait for the game process to be available (blocking poll)
function wait_for_process(name)
    while true do
        local pid = spectre.find_process(name)
        if pid then
            bot.log("Found process " .. name .. " (PID: " .. pid .. ")")
            return pid
        end
        bot.log("Waiting for " .. name .. " ...")
        bot.wait(5000)
    end
end

-- Read a value; on failure (e.g. a placeholder address) log and return nil
-- instead of aborting the script.
function try_read(read, pid, addr)
    local ok, value = pcall(read, pid, addr)
    if ok then
        return value
    end
    bot.log("  read at " .. hex(addr) .. " failed: " .. tostring(value):match("[^\n]*"))
    return nil
end

-- ── Mode "safe_claim" ──────────────────────────────────────────────

function safe_claim_loop(pid)
    local round = 0
    while true do
        round = round + 1
        bot.log("=== Claim round " .. round .. " ===")

        -- read_u64 also fits the i64 gold field while gold is positive
        local gold = try_read(spectre.read_u64, pid, OFFSET_GOLD)
        local exp  = try_read(spectre.read_u64, pid, OFFSET_EXP)
        bot.log("  Gold: " .. tostring(gold) .. "  EXP: " .. tostring(exp))

        -- Weak guard: skips only an unreadable address or an implausible value;
        -- a wrong but readable address (stale, a copy) usually still clicks.
        if gold and gold > 0 and gold < 10000000000 then
            bot.log("  Opening Login Rewards → Claim")
            bot.click(BTN_LOGIN_REWARDS.x, BTN_LOGIN_REWARDS.y)
            bot.wait(1500)
            bot.click(BTN_CLAIM.x, BTN_CLAIM.y)
            bot.wait(2000)

            -- A change by the claimed amount supports the gold offset; no change
            -- proves nothing if today's reward had no gold (or nothing to claim).
            local after = try_read(spectre.read_u64, pid, OFFSET_GOLD)
            if after then
                bot.log("  Gold after claim: " .. after .. "  (delta " .. (after - gold) .. ")")
            end
        else
            bot.log("  Gold not readable or out of range — not clicking (REPLACE OFFSET_GOLD?)")
        end

        bot.wait(CLAIM_INTERVAL)
    end
end

-- ── Main Loop ──────────────────────────────────────────────────────

local pid = wait_for_process(TARGET_PROCESS)

if MODE == "safe_claim" then
    safe_claim_loop(pid)
    return
end

local cycle = 0

while true do
    cycle = cycle + 1
    bot.log("=== Cycle " .. cycle .. " ===")

    -- Check battle state
    local battle_state = spectre.read_u32(pid, OFFSET_BATTLE)
    local hp           = spectre.read_u32(pid, OFFSET_HP)
    local energy       = spectre.read_u32(pid, OFFSET_ENERGY)

    bot.log("  Battle: " .. battle_state .. "  HP: " .. hp .. "  Energy: " .. energy)

    if battle_state == 1 then
        -- In battle — tap Skip button
        bot.log("  In battle → tapping Skip")
        bot.click(BTN_SKIP.x, BTN_SKIP.y)
        bot.wait(500)

    elseif battle_state == 2 then
        -- Victory screen — collect rewards
        bot.log("  Victory → collecting rewards")
        bot.click(BTN_COLLECT.x, BTN_COLLECT.y)
        bot.wait(1000)
        bot.click(BTN_COLLECT.x, BTN_COLLECT.y)
        bot.wait(1000)

        -- Start next battle
        bot.click(BTN_START.x, BTN_START.y)
        bot.wait(CYCLE_WAIT)

    else
        -- Idle or unknown — poll
        bot.log("  Idle — polling")
        bot.wait(POLL_INTERVAL)

        -- If HP is very low, add a longer recovery wait
        if hp > 0 and hp < 100 then
            bot.log("  Low HP (" .. hp .. ") — resting 30s")
            bot.wait(30000)
        end
    end

    -- Safety: don't spin faster than 200ms
    bot.wait(200)
end