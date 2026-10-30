-- AFK Journey — AFK bot example for Spectre
-- Runs an automated loop: checks battle status, collects rewards, starts next fight.
--
-- Usage:  spectre script examples/afk-bot.lua --input-backend adb

bot.log("=== AFK Journey Bot Starting ===")

-- ── Configuration ──────────────────────────────────────────────────
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

-- ── Main Loop ──────────────────────────────────────────────────────

local pid = wait_for_process(TARGET_PROCESS)
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