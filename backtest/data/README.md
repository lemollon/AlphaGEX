# Backtest Data

Large parquet files are **not checked into this repo**. They used to live in
Git LFS but repeatedly exceeded the GitHub LFS budget and blocked every Render
deploy. The LFS tracking was removed on 2026-04-14 and the file is now kept out
of Git entirely.

## Which file

`spy_options.parquet` (~632 MB) — a consolidated SPY options chain dataset
historically derived from philippdubach's public options data plus custom
Tradier/Polygon fills.

## Who needs it

Only the two manual CLI scripts below need this file. **No deployed Render
service reads it**, so deploys are unaffected:

- `backtest/spark_flame_backtest.py` (SPARK/FLAME backtest runner)
- `backtest/data_audit.py` (schema + DTE coverage audit)

Running either script without the file produces a clear `FileNotFoundError`
that points back at this README.

## How to obtain it locally

Ask the team for the current download location (S3 bucket, Google Drive,
direct share) and place the file at:

```
backtest/data/spy_options.parquet
```

The scripts accept a `--parquet` flag if you want to keep it elsewhere:

```
python backtest/spark_flame_backtest.py --parquet /path/to/your/spy_options.parquet
```

## Why not LFS / S3 / release asset

- **LFS**: exhausted the repo's monthly bandwidth budget every few weeks. Blocked Render deploys.
- **S3 / object storage**: would work but requires credentials; not worth the overhead for a file that's only used ad-hoc in local dev.
- **GitHub Release asset**: possible future option (file is under the 2 GB limit). If we standardize on that, a download helper goes here and in `spark_flame_backtest.py::load_options_data`.

For now: keep the file local, off Git. Clean and quiet.
