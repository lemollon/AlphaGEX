# Autonomous Trader Auto-Start Setup

## Problem
The autonomous trader is fully configured but not running automatically. It needs to start on system boot and restart if it crashes.

## Solution: Add to Crontab

Run this command **on your actual system** (not in this sandboxed environment):

```bash
cd /home/user/AlphaGEX

# Add to crontab
(crontab -l 2>/dev/null; echo "@reboot /home/user/AlphaGEX/auto_start_trader.sh") | crontab -
```

This will:
- ✅ Start the autonomous trader automatically when your system boots
- ✅ Run every day during market hours (8:30 AM - 3:00 PM CT)
- ✅ Scan for trades every 5 minutes
- ✅ Execute minimum 1 trade per day

## Manual Start (Until Next Reboot)

To start it immediately without waiting for a reboot:

```bash
cd /home/user/AlphaGEX
./auto_start_trader.sh
```

## Verify It's Running

```bash
# Check if trader is running
ps aux | grep autonomous_scheduler

# Check the PID
cat /home/user/AlphaGEX/logs/trader.pid

# Watch the logs
tail -f /home/user/AlphaGEX/logs/trader.log
```

## Check Trade Activity

```bash
cd /home/user/AlphaGEX/backend
sqlite3 gex_copilot.db "SELECT COUNT(*) FROM autonomous_trader_logs"
sqlite3 gex_copilot.db "SELECT COUNT(*) FROM positions"

# See latest activity
sqlite3 gex_copilot.db "SELECT timestamp, action_taken, reasoning_summary FROM autonomous_trader_logs ORDER BY timestamp DESC LIMIT 5"
```

## Stop the Trader (If Needed)

```bash
# Kill by PID
kill $(cat /home/user/AlphaGEX/logs/trader.pid)

# Or find and kill
pkill -f autonomous_scheduler
```

## Logs Location

- Main logs: `/home/user/AlphaGEX/logs/trader.log`
- Error logs: `/home/user/AlphaGEX/logs/trader.error.log`
- PID file: `/home/user/AlphaGEX/logs/trader.pid`

## What It Does Automatically

Once running, the trader will:

1. **Wake up at market open** (8:30 AM CT)
2. **Scan every 5 minutes** during market hours
3. **Detect setups** using Psychology Trap Detection
4. **Execute trades** automatically (minimum 1 per day)
5. **Manage positions** (exit at targets/stops)
6. **Log everything** to database
7. **Sleep after market close** (3:00 PM CT)
8. **Repeat daily** Monday-Friday

## Why It Wasn't Running

The autonomous trader was **configured but never started**. It's like having a car with the keys in the ignition - ready to go, but someone needs to turn it on (or set up auto-start).

Now with the crontab entry, it will start automatically on system boot and run continuously.

## Start It Right Now

```bash
cd /home/user/AlphaGEX
./auto_start_trader.sh

# Verify
tail -f logs/trader.log
```

Market is open for another ~20 minutes today - start it now to potentially catch a trade!
