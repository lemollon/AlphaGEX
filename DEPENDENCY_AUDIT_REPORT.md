# AlphaGEX Dependency Audit Report

**Date:** 2025-12-25
**Auditor:** Claude Code

## Executive Summary

This audit analyzed all Python and JavaScript dependencies across 6 requirement files. The analysis identified:
- **14+ security vulnerabilities** across Python packages
- **3 npm vulnerabilities** in the frontend
- **4 unused dependencies** that can be removed
- **Multiple version conflicts** across requirement files
- Recommendations for consolidation and modernization

---

## 1. Security Vulnerabilities (CRITICAL)

### Python Packages - High Priority

| Package | Current Version | Vulnerability | Fix Version | Severity |
|---------|----------------|---------------|-------------|----------|
| `fastapi` | 0.109.0 | PYSEC-2024-38 | ≥0.109.1 | Medium |
| `python-multipart` | 0.0.6 | CVE-2024-24762, CVE-2024-53981 | ≥0.0.18 | High |
| `aiohttp` | 3.9.1 | CVE-2024-27306, CVE-2024-30251, CVE-2024-52304, CVE-2025-53643 | ≥3.12.14 | High |
| `python-jose` | 3.3.0 | PYSEC-2024-232, PYSEC-2024-233 | ≥3.4.0 | High |
| `starlette` | 0.35.1 (transitive) | CVE-2024-47874, CVE-2025-54121 | ≥0.47.2 | High |
| `requests` | 2.31.0 | CVE-2024-35195, CVE-2024-47081 | ≥2.32.4 | Medium |
| `langchain-core` | 0.2.43 | CVE-2025-65106, CVE-2025-68664 | ≥0.3.81 | Medium |
| `langchain-community` | 0.2.19 | CVE-2025-6984 | ≥0.3.27 | Medium |
| `ecdsa` | 0.19.1 (transitive) | CVE-2024-23342 | No fix yet | Medium |

### JavaScript Packages (Frontend)

| Package | Current Version | Vulnerability | Fix |
|---------|----------------|---------------|-----|
| `next` | 14.2.33 | DoS via Server Components (GHSA-mwv6-3258-q52c) | ≥14.2.35 |
| `js-yaml` | 4.0.0-4.1.0 | Prototype pollution (GHSA-mh29-5h37-fv8m) | Run `npm audit fix` |
| `glob` | 10.2.0-10.4.5 | Command injection (GHSA-5j98-mcp5-4vw2) | Run `npm audit fix` |

---

## 2. Unused/Unnecessary Dependencies (BLOAT)

These packages are listed in requirements but **not imported anywhere** in the codebase:

| Package | File | Recommendation |
|---------|------|----------------|
| `twilio>=8.10.0` | requirements.txt | **REMOVE** - No imports found in any Python file |
| `py_vollib>=1.0.1` | requirements.txt | **REMOVE** - Custom IV solver in `quant/iv_solver.py` is used instead |
| `langsmith>=0.0.70` | requirements.txt | **REMOVE** - Not imported anywhere |
| `multitasking>=0.0.7` | requirements.txt | **KEEP** - Transitive dependency of `yfinance` |

### Redundant Scheduling Libraries

Both `schedule` and `apscheduler` are included:
- `apscheduler` - Used in 11 files (main scheduler)
- `schedule` - Used in only 1 file (`data/automated_data_collector.py`)

**Recommendation:** Consider migrating `automated_data_collector.py` to use `apscheduler` exclusively to reduce dependencies.

---

## 3. Version Conflicts Across Files

### LangChain Ecosystem (CRITICAL CONFLICT)

| Package | requirements.txt | requirements-render.txt | requirements-ai.txt | backend/requirements.txt |
|---------|-----------------|------------------------|---------------------|-------------------------|
| langchain | ≥0.1.0 | ≥0.3.0 | ==0.1.0 | ≥0.1.0 |
| langchain-anthropic | ≥0.1.0 | ≥0.3.0 | ==0.1.1 | ≥0.1.0 |
| langchain-community | ≥0.0.20 | ≥0.3.0 | ==0.0.20 | ≥0.0.20 |
| langchain-core | ≥0.1.0 | ≥0.3.0 | N/A | N/A |

**Risk:** This can cause dependency resolution failures or inconsistent behavior between environments.

### Pydantic Versions

| File | Version |
|------|---------|
| requirements.txt | ≥2.5.0 |
| requirements-render.txt | ≥2.7.4,<3.0.0 |
| requirements-ai.txt | ==2.5.0 |
| backend/requirements.txt | ==2.5.3 |

### FastAPI Versions

| File | Version |
|------|---------|
| requirements.txt | ≥0.104.0 |
| requirements-render.txt | ==0.109.0 |
| backend/requirements.txt | ==0.109.0 |

---

## 4. Outdated Packages

### Python - Significantly Outdated

| Package | Current | Latest | Gap |
|---------|---------|--------|-----|
| fastapi | 0.109.0 | 0.127.0 | 18 minor versions |
| aiohttp | 3.9.1 | 3.12.14 | 3 minor versions |
| uvicorn | 0.27.0 | 0.34.0+ | 7 minor versions |
| pandas | 2.1.4 | 2.2.3 | 1 minor version |
| numpy | 1.26.2 | 2.2.1 | Major version |

### JavaScript - Significantly Outdated

| Package | Current | Latest | Notes |
|---------|---------|--------|-------|
| react | 18.2.0 | 19.2.3 | Major version available |
| next | 14.2.33 | 16.1.1 | 2 major versions behind |
| tailwindcss | 3.4.0 | 4.1.18 | Major version available |
| lucide-react | 0.294.0 | 0.562.0 | Very outdated |
| date-fns | 2.30.0 | 4.1.0 | 2 major versions |
| lightweight-charts | 4.1.1 | 5.1.0 | Major version |
| recharts | 2.10.3 | 3.6.0 | Major version |

---

## 5. Recommendations

### Immediate Actions (Security)

1. **Update vulnerable packages in `requirements-render.txt` and `backend/requirements.txt`:**
   ```
   fastapi>=0.115.0
   python-multipart>=0.0.18
   aiohttp>=3.12.14
   python-jose[cryptography]>=3.4.0
   requests>=2.32.5
   ```

2. **Update LangChain ecosystem consistently:**
   ```
   langchain>=0.3.0
   langchain-anthropic>=0.3.0
   langchain-community>=0.3.27
   langchain-core>=0.3.81
   ```

3. **Fix frontend vulnerabilities:**
   ```bash
   cd frontend && npm audit fix
   ```

### Short-term Actions (Cleanup)

1. **Remove unused dependencies from `requirements.txt`:**
   - Remove `twilio>=8.10.0`
   - Remove `py_vollib>=1.0.1`
   - Remove `langsmith>=0.0.70`

2. **Consolidate requirement files:**
   - Consider merging `requirements.txt`, `requirements-render.txt`, and `requirements-ai.txt` into a single source of truth
   - Use optional dependencies groups: `pip install .[render]` or `pip install .[ai]`

### Long-term Considerations

1. **Frontend Framework Updates:**
   - React 19 and Next.js 16 are major updates with breaking changes
   - Plan a dedicated upgrade sprint with thorough testing

2. **Consider using `pyproject.toml`:**
   - Modern Python packaging standard
   - Better dependency management with groups
   - Easier to maintain version constraints

3. **Add dependency scanning to CI/CD:**
   - GitHub Dependabot or Snyk for automated vulnerability alerts
   - `pip-audit` in pre-commit hooks or CI

---

## 6. Consolidated Recommended Versions

### Python Core Dependencies (Security-Patched)

```txt
# Core Framework
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.18
starlette>=0.40.0

# HTTP Clients
aiohttp>=3.12.14
httpx>=0.27.0
requests>=2.32.5

# Security
python-jose[cryptography]>=3.4.0
passlib[bcrypt]>=1.7.4

# Data
pandas>=2.1.4
numpy>=1.26.0
scipy>=1.11.0

# AI/ML
langchain>=0.3.0
langchain-anthropic>=0.3.0
langchain-community>=0.3.27
langchain-core>=0.3.81
anthropic>=0.40.0
scikit-learn>=1.3.0
xgboost>=2.0.0,<3.0.0

# Database
sqlalchemy>=2.0.25
psycopg2-binary>=2.9.9
alembic>=1.13.1

# Other
pydantic>=2.7.4,<3.0.0
pydantic-settings>=2.3.0
yfinance>=0.2.50
pytz>=2023.3
apscheduler>=3.10.4
python-dotenv>=1.0.0
websockets>=12.0
pyyaml>=6.0.1
redis>=5.0.1
plotly>=5.18.0
```

### Frontend Dependencies (Stable Updates)

```json
{
  "next": "^14.2.35",
  "lucide-react": "^0.460.0",
  "postcss": "^8.4.49",
  "autoprefixer": "^10.4.20"
}
```

---

## Summary Table

| Category | Items Found | Priority |
|----------|-------------|----------|
| Security Vulnerabilities (Python) | 14+ | **CRITICAL** |
| Security Vulnerabilities (JS) | 3 | **HIGH** |
| Unused Dependencies | 4 | MEDIUM |
| Version Conflicts | 8+ packages | **HIGH** |
| Outdated Packages | 20+ | LOW-MEDIUM |

**Estimated Effort:** 2-4 hours for security patches, 1-2 days for full modernization
