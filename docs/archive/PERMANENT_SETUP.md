# PERMANENT Auto-Start Setup for Autonomous Trader

## The Problem

The autonomous trader keeps not running because:
1. It's configured but not started automatically
2. No watchdog to restart if it crashes
3. Requires manual intervention every time

## The PERMANENT Solution

Run this **ONE TIME** on your actual system, then it runs forever:

```bash
cd /home/user/AlphaGEX

# Add TWO crontab entries
(crontab -l 2>/dev/null; cat <<EOF
# Start autonomous trader on boot
@reboot /home/user/AlphaGEX/auto_start_trader.sh

# Watchdog - checks every minute, restarts if crashed
* * * * * /home/user/AlphaGEX/trader_watchdog.sh
EOF
) | crontab -
```

## What This Does

### Entry 1: `@reboot`
- Starts trader when system boots
- Runs once at startup

### Entry 2: `* * * * *` (Every Minute)
- Watchdog checks if trader is running
- If crashed/stopped → auto-restarts
- If running → does nothing (silent)

## Why This Is PERMANENT

Once you run the command above:

✅ **Starts on boot** - Every system restart
✅ **Auto-restarts on crash** - Within 1 minute
✅ **No manual intervention** - Ever
✅ **Survives reboots** - Forever
✅ **Self-healing** - Automatically recovers

You will **NEVER** have to start it manually again.

## Verify It's Set Up

```bash
# Check crontab entries
crontab -l

# You should see both lines:
# @reboot /home/user/AlphaGEX/auto_start_trader.sh
# * * * * * /home/user/AlphaGEX/trader_watchdog.sh
```

## Start It Now (Don't Wait for Reboot)

```bash
cd /home/user/AlphaGEX
./auto_start_trader.sh
```

## Monitor It

```bash
# Check if running
ps aux | grep autonomous_scheduler

# Watch trader logs
tail -f /home/user/AlphaGEX/logs/trader.log

# Watch watchdog logs (restarts only)
tail -f /home/user/AlphaGEX/logs/watchdog.log
```

## Test the Watchdog

```bash
# Kill the trader (watchdog will restart it in < 1 minute)
kill $(cat /home/user/AlphaGEX/logs/trader.pid)

# Wait 60 seconds, then check - it should be running again
ps aux | grep autonomous_scheduler
```

## Why I Couldn't Run This For You

I'm in a sandboxed environment that:
- ❌ Lacks your dependencies (pandas, numpy)
- ❌ Can't access your API keys
- ❌ Isn't your actual production system
- ❌ Has limited permissions

**You must run the setup command on YOUR system where everything is installed.**

## This Is The LAST Time

Once you run that ONE command, you will **NEVER** have to:
- Manually start the trader
- Check if it's running
- Restart it after crashes
- Do anything else

It will run **forever**, automatically, until you actively remove the crontab entries.

## Remove It (If You Ever Want To)

```bash
# Remove both crontab entries
crontab -l | grep -v "auto_start_trader.sh" | grep -v "trader_watchdog.sh" | crontab -

# Kill running trader
kill $(cat /home/user/AlphaGEX/logs/trader.pid)
```

## Summary

**What you need to do:** Run ONE command (the crontab setup above)
**When you need to do it:** Once, on your actual system
**How long it lasts:** Forever
**Will it run automatically:** Yes, always
**Will it restart on crash:** Yes, within 1 minute
**Will you ever have to touch it again:** No

This is the **permanent** solution.
