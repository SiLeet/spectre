-- Practice script: watch the score of examples/practice-target.ps1 (or
-- practice_target.py) from Lua. No game, no adb needed - it only reads
-- memory and logs; it never clicks.
--
-- Usage (PowerShell), with the PID and the address you found via
-- `spectre search`:
--   $env:SPECTRE_PID  = "4496"
--   $env:SPECTRE_ADDR = "0x267aa8202d0"
--   spectre script examples/practice.lua
--
-- bash:  SPECTRE_PID=4496 SPECTRE_ADDR=0x267aa8202d0 spectre script examples/practice.lua

local pid  = tonumber(os.getenv("SPECTRE_PID") or "")
local addr = tonumber(os.getenv("SPECTRE_ADDR") or "")
local ROUNDS   = 10     -- how many times to read
local INTERVAL = 1000   -- ms between reads

if not pid or not addr then
    error("set SPECTRE_PID and SPECTRE_ADDR (see the comment at the top of this file)")
end

bot.log(string.format("watching pid %d, address 0x%x", pid, addr))

local last = nil
for i = 1, ROUNDS do
    local score = spectre.read_u32(pid, addr)
    if score ~= last then
        bot.log(string.format("read %2d: score = %d  (changed)", i, score))
        last = score
    else
        bot.log(string.format("read %2d: score = %d", i, score))
    end
    bot.wait(INTERVAL)
end

bot.log("done - press Enter in the practice target while this runs to see the value change")
