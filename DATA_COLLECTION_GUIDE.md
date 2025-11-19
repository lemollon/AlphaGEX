# AlphaGEX Automated Data Collection System

## Overview

The automated data collector runs all data collection jobs periodically during market hours to keep your database populated with fresh data.

---

## 📅 Collection Schedule

| Job | Frequency | When |
|-----|-----------|------|
| **GEX History** | Every 15 minutes | Market hours |
| **Liberation Outcomes** | Every 30 minutes | Market hours |
| **Forward Magnets** | Every 15 minutes | Market hours |
| **Gamma Expiration** | Every 60 minutes | Market hours |
| **Daily Performance** | Once daily | 4:00 PM ET (after close) |

**Market Hours:** 9:30 AM - 4:00 PM ET (Monday-Friday)

---

## 🚀 Quick Start

### Option 1: Manual Control (Recommended for testing)

Start the collector:
```bash
./manage_collector.sh start
```

Check status:
```bash
./manage_collector.sh status
```

View live logs:
```bash
./manage_collector.sh logs
```

Stop the collector:
```bash
./manage_collector.sh stop
```

### Option 2: Run as System Service (Production)

Install as systemd service:
```bash
sudo ./manage_collector.sh install
```

Start the service:
```bash
sudo systemctl start alphagex-collector
```

Enable auto-start on boot:
```bash
sudo systemctl enable alphagex-collector
```

Check status:
```bash
sudo systemctl status alphagex-collector
```

View logs:
```bash
sudo journalctl -u alphagex-collector -f
```

---

## 📋 Management Commands

```bash
./manage_collector.sh start     # Start the collector
./manage_collector.sh stop      # Stop the collector
./manage_collector.sh restart   # Restart the collector
./manage_collector.sh status    # Check if running
./manage_collector.sh logs      # View live logs
./manage_collector.sh install   # Install as system service (needs sudo)
./manage_collector.sh help      # Show help
```

---

## 📂 Log Files

Logs are stored in `/home/user/AlphaGEX/logs/`:

- `data_collector.log` - Main log file with all collection activity
- `data_collector_error.log` - Error log (when running as service)

---

## 🔍 What Gets Collected

### 1. GEX History (Every 15 min)
- Net GEX snapshots
- Flip point tracking
- Call/put walls
- Regime changes
- **Populates:** `gex_history` table

### 2. Liberation Outcomes (Every 30 min)
- Validates psychology trap predictions
- Checks if targets were hit
- Calculates prediction accuracy
- **Populates:** `liberation_outcomes` table

### 3. Forward Magnets (Every 15 min)
- Detects high gamma strikes
- Tracks if price reaches magnets
- Measures magnet effectiveness
- **Populates:** `forward_magnets` table

### 4. Gamma Expiration Timeline (Every 60 min)
- Snapshots gamma by DTE buckets
- Tracks gamma concentration
- Dealer hedging patterns
- **Populates:** `gamma_expiration_timeline` table

### 5. Daily Performance (Once at close)
- Calculates Sharpe ratio
- Max drawdown tracking
- Win rate analysis
- P&L aggregation
- **Populates:** `performance` table

---

## ⚠️ Troubleshooting

### Collector won't start

**Check Python version:**
```bash
python3 --version  # Should be 3.9+
```

**Check dependencies:**
```bash
pip3 install schedule
```

**Check logs:**
```bash
tail -50 logs/data_collector.log
```

### No data being collected

**Verify market hours:**
- Collector only runs 9:30 AM - 4:00 PM ET (Mon-Fri)
- Check current time: `date`

**Check if running:**
```bash
./manage_collector.sh status
```

**Manually test collectors:**
```bash
python3 run_all_data_collectors.py
```

### High CPU usage

This is normal during collection runs. Each job takes 2-10 seconds.

If persistent:
- Check for stuck processes: `ps aux | grep python`
- Restart collector: `./manage_collector.sh restart`

---

## 🎯 Verifying Data Collection

### Check database tables:

```bash
sqlite3 alpha_gex.db "SELECT COUNT(*) FROM gex_history;"
sqlite3 alpha_gex.db "SELECT COUNT(*) FROM liberation_outcomes;"
sqlite3 alpha_gex.db "SELECT COUNT(*) FROM forward_magnets;"
sqlite3 alpha_gex.db "SELECT COUNT(*) FROM gamma_expiration_timeline;"
sqlite3 alpha_gex.db "SELECT COUNT(*) FROM performance;"
```

### View recent GEX snapshots:

```bash
sqlite3 alpha_gex.db "SELECT timestamp, net_gex, regime FROM gex_history ORDER BY timestamp DESC LIMIT 5;"
```

### Check liberation accuracy:

```bash
sqlite3 alpha_gex.db "SELECT signal_type, COUNT(*), AVG(CASE WHEN prediction_correct=1 THEN 100.0 ELSE 0 END) as accuracy FROM liberation_outcomes GROUP BY signal_type;"
```

---

## 🔐 Security Notes

- Logs may contain market data - protect accordingly
- PID file stored in `logs/collector.pid`
- Service runs as root user (can be changed in service file)

---

## 💡 Tips

1. **Start before market open** to catch the opening data
2. **Monitor logs initially** to ensure everything works
3. **Check database size** periodically: `du -h alpha_gex.db`
4. **Backup database daily** before 9:30 AM
5. **Review accuracy metrics** weekly to validate strategies

---

## 🆘 Support

If data collection fails:

1. Check logs: `./manage_collector.sh logs`
2. Verify Python dependencies: `pip3 list | grep schedule`
3. Test individual collectors: `python3 liberation_outcomes_tracker.py`
4. Check database permissions: `ls -l alpha_gex.db`

---

## 📊 Expected Data Volume

Per trading day (6.5 hours):

- GEX History: ~26 snapshots (15-min intervals)
- Liberation Outcomes: ~13 checks (30-min intervals)
- Forward Magnets: ~26 detections (15-min intervals)
- Gamma Expiration: ~7 snapshots (60-min intervals)
- Daily Performance: 1 aggregation

**Total:** ~73 database inserts per day

**Database growth:** ~500 KB - 2 MB per trading day
