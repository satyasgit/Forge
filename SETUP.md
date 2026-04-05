# AI Agent Org - End-to-End Setup Guide

**Version**: Phase 4 (Repository complete)
**Last Updated**: 2026-04-05
**Time to E2E**: ~10-15 minutes

---

## Quick Start (TL;DR)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure database (choose one):

## Option A: SQLite (Easiest - No PostgreSQL needed)
# Edit config/settings.py, line 32:
# Change: database_url: str = "postgresql://postgres:postgres@localhost:5432/ai_agent_org"
# To:     database_url: str = ""
# OR set in .env: DATABASE_URL=

## Option B: PostgreSQL (Production-like)
pip install psycopg2-binary
createdb ai_agent_org
# Ensure .env has: DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_agent_org

# 3. Set Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> .env

# 4. Create directories
mkdir -p data workspace

# 5. Start API server
.venv/bin/uvicorn api.main:app --reload --port 8000

# 6. Verify
curl http://localhost:8000/api/pipelines/health
curl http://localhost:8000/api/projects/default/pipelines/history
```

---

## Detailed Setup

### 1. Prerequisites

- **Python**: 3.11+ (3.13 tested)
- **Node.js**: 18+ (for React UI)
- **PostgreSQL**: 14+ (optional, only if not using SQLite)
- **Anthropic API Key**: Get from https://console.anthropic.com

### 2. Install Python Dependencies

```bash
# Clone and setup virtualenv (if not done)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# IMPORTANT: If using PostgreSQL, install driver:
pip install psycopg2-binary  # Pre-compiled wheels (easier)
# OR (if psycopg2-binary fails) install system deps then psycopg2:
#   brew install postgresql  # macOS
#   sudo apt-get install libpq-dev python3-dev  # Ubuntu/Debian
#   pip install psycopg2
```

**Note**: `requirements.txt` includes `asyncpg` (PostgreSQL async driver) but NOT `psycopg2`. The sync engine uses `psycopg2`/`psycopg2-binary`. You need one of them for PostgreSQL.

### 3. Database Configuration

#### Option A: SQLite (Development - Recommended to start)

**Advantages**: No external service, instant setup, file-based.

1. Edit `config/settings.py` OR set in `.env`:

```python
# In config/settings.py, change line 32:
database_url: str = ""  # Empty string → uses SQLite fallback
```

OR in `.env`:
```bash
DATABASE_URL=
```

2. The application will use:
   - **Repository DB**: SQLite at `data/pipelines.db` (auto-created)
   - **Memory DB**: SQLite at `data/agent_memory.db` (already configured)

3. No need to create database manually.

#### Option B: PostgreSQL (Production-like)

1. Install PostgreSQL locally:
   ```bash
   # macOS
   brew install postgresql
   brew services start postgresql

   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib
   sudo service postgresql start
   ```

2. Create database:
   ```bash
  sudo -u postgres createdb ai_agent_org
   # Or if no sudo: createdb ai_agent_org (if your user has access)
   ```

3. Ensure connection string in `.env`:
   ```bash
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_agent_org
   ```

   Adjust username/password as needed.

4. Test connection:
   ```bash
   psql ai_agent_org -c "SELECT 1;"
   ```

### 4. Environment Variables (.env)

Copy `.env.example` to `.env` and fill in required values:

```bash
# Required (set these!)
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here  # Get from console.anthropic.com

# Database (see step 3)
# DATABASE_URL=  # Empty for SQLite, or postgresql://... for PostgreSQL

# Optional (defaults are fine for dev)
MODEL=claude-opus-4-5
FAST_MODEL=claude-haiku-4-5-20251001
MAX_TOKENS=4096
MEMORY_DB_PATH=data/agent_memory.db

API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=dev-secret-key-change-in-prod

MAX_PIPELINE_COST_USD=5.00

ENABLE_COST_TRACKING=true
ENABLE_SLACK_NOTIFICATIONS=false
ENABLE_JIRA_INTEGRATION=false
ENABLE_GITHUB_INTEGRATION=false
```

### 5. Create Required Directories

```bash
mkdir -p data workspace logs

# Optional: create separate database directories
mkdir -p data/{pipelines,memory}
```

The app tries to create `data/` and `workspace/` on startup, but better to create manually to avoid permission issues.

### 6. Initialize Database (PostgreSQL only)

If using SQLite: tables auto-created on first run. Skip to step 7.

If using PostgreSQL: tables created automatically when models are imported. You can force creation:

```bash
# Method 1: Let FastAPI create on first request (automatic)
# Just start the server, tables created when first DB operation occurs

# Method 2: Explicit initialization
python3 -c "
import asyncio
from pipeline.models_database import init_db
asyncio.run(init_db())
"
```

This runs:
```python
async def init_db():
    from pipeline import models_database
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### 7. Start the API Server

```bash
# Activate virtualenv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows

# Start FastAPI with hot reload
uvicorn api.main:app --reload --port 8000

# Or using the module:
.venv/bin/python -m uvicorn api.main:app --reload --port 8000
```

Expected output:
```
INFO:     Will watch for changes in these directories: ['...']
INFO:     Started reloader process [12345]
INFO:     Started server process [12367]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 8. Verify Installation

#### 8.1 Health Check

```bash
curl http://localhost:8000/api/pipelines/health
```

Expected response:
```json
{
  "status": "ok",
  "features": ["templates", "validation", "preview", "run"]
}
```

#### 8.2 List Templates

```bash
curl http://localhost:8000/api/pipelines/templates
```

Should return JSON with 4 templates (full_stack_web, api_only, security_audit_only, mvp).

#### 8.3 History Endpoint (New!)

```bash
curl "http://localhost:8000/api/projects/default/pipelines/history?limit=10"
```

Expected (empty initially):
```json
{
  "project_id": "default",
  "runs": [],
  "total_cost_usd": 0.0
}
```

#### 8.4 Run a Simple Pipeline

```bash
curl -X POST http://localhost:8000/api/pipelines/run \
  -H "Content-Type: application/json" \
  -d '{
    "feature": "Test API pipeline",
    "project_id": "test",
    "config": {
      "name": "test_run",
      "description": "Quick test",
      "agents": [
        {"agent": "pm", "enabled": true}
      ]
    }
  }'
```

Response:
```json
{
  "success": true,
  "run": {
    "job_id": "abc123...",
    "status": "pending"
  },
  "message": "Pipeline started"
}
```

Check status:
```bash
curl http://localhost:8000/api/pipeline/jobs/<job_id>
```

After completion, check history:
```bash
curl "http://localhost:8000/api/projects/test/pipelines/history"
```

Should now show the completed run with cost, duration, etc.

### 9. Run Tests

```bash
# Repository tests (SQLite in-memory, always work)
.venv/bin/pytest tests/pipeline/test_repository.py -v

# Config loader tests
.venv/bin/pytest tests/pipeline/test_config_loader.py -v

# All pipeline tests
.venv/bin/pytest tests/pipeline/ -v

# API tests (need database configured)
.venv/bin/pytest tests/api/test_pipelines.py -v
```

Expected: All pipeline tests pass (59/59). API tests may have some fixture issues if DB not set up correctly.

---

## 10. Start the React UI (Optional)

```bash
cd pipeline-ui

# Install dependencies (first time only)
npm install

# Start dev server
npm run dev

# Open http://localhost:5173 in browser
```

The UI should connect to API at `http://localhost:8000` by default (see `pipeline-ui/src/api.ts`).

To build for production:
```bash
cd pipeline-ui
npm run build
# Output in pipeline-ui/dist/
```

Serve with any static file server (e.g., `npx serve pipeline-ui/dist`).

---

## 11. Common Issues & Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'psycopg2'`

**Cause**: Using PostgreSQL but psycopg2 not installed.

**Fix**:
```bash
pip install psycopg2-binary
```
OR switch to SQLite by setting `DATABASE_URL=` empty.

### Issue: `psycopg2` installation fails on macOS/Linux

**Cause**: Missing libpq development files.

**Fix**:
```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install libpq-dev python3-dev

# Then try again
pip install psycopg2-binary
```

### Issue: Database connection refused

**Cause**: PostgreSQL not running or wrong credentials.

**Fix**:
```bash
# Check PostgreSQL is running
brew services list  # macOS
sudo service postgresql status  # Linux

# Start if stopped
brew services start postgresql  # macOS
sudo service postgresql start  # Linux

# Test connection
psql ai_agent_org -h localhost -U postgres
```

### Issue: Permission denied on database

**Cause**: Your user doesn't have access to `ai_agent_org` database.

**Fix**:
```bash
# Connect as postgres superuser
sudo -u postgres psql

# Grant access (replace 'youruser' with your system username)
GRANT ALL PRIVILEGES ON DATABASE ai_agent_org TO youruser;
\q
```

Or create the DB as your current user:
```bash
createdb ai_agent_org  # If your user has create_db privilege
```

### Issue: `ANTHROPIC_API_KEY` not set

**Cause**: Missing or invalid API key in `.env`.

**Fix**:
1. Get key from https://console.anthropic.com
2. Add to `.env`:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Restart server (FastAPI reads `.env` at startup via Pydantic)

### Issue: History endpoint returns 500 error

**Cause**: Logger not defined or database not initialized.

**Fix**:
1. Check logs for exact error
2. Ensure `logger = logging.getLogger(__name__)` is in `api/main.py` (added in Phase 4)
3. If DB error: initialize database (see step 6)

### Issue: Tests fail with `ImportError` during collection

**Cause**: Server-level Python packages missing (psycopg2, pytest, etc.)

**Fix**:
```bash
# Activate virtualenv
source .venv/bin/activate

# Install all requirements
pip install -r requirements.txt

# Install test dependencies (if separate)
pip install pytest pytest-asyncio pytest-cov
```

### Issue: React UI cannot connect to API (CORS error)

**Cause**: API CORS configuration doesn't include UI origin.

**Fix**: Currently configured for `http://localhost:3000` and `http://localhost:5173` (Vite default). If using different port, add to `api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Add your UI origin
    ...
)
```

---

## 12. Verify Full E2E Flow

When everything is working:

1. **Start API**: `uvicorn api.main:app --reload`
2. **Start UI** (optional): `cd pipeline-ui && npm run dev`
3. **Open UI**: http://localhost:5173
4. **Build Pipeline**:
   - Drag PM agent to canvas
   - Drag Backend agent, connect PM → Backend
   - Click "Preview" → see cost estimate
   - Click "Run" → pipeline executes
5. **Check History**:
   - Navigate to History tab (if implemented) or:
   - `curl http://localhost:8000/api/projects/default/pipelines/history`
   - Should show the completed run with details
6. **View in Database** (optional):
   ```sql
   SELECT id, config->>'name', status, total_cost, created_at
   FROM pipeline_runs
   ORDER BY created_at DESC;
   ```

---

## 13. What's Working vs. Not Yet

### ✅ Working (E2E)

- [x] API server with all endpoints
- [x] Template loading and validation
- [x] Preview with cost/DAG estimation
- [x] Custom pipeline execution (async jobs)
- [x] Job status polling
- [x] Checkpoint creation and resume
- [x] Repository layer (SQLite + PostgreSQL)
- [x] History API returning DB data
- [x] React UI pipeline builder (frontend only, integrates with API)

### ⏳ In Progress / Needs Setup

- [ ] History UI component (need to wire API to React)
- [ ] Template import/export (save custom templates)
- [ ] Analytics dashboard
- [ ] CLI tool
- [ ] Alembic migrations (dev uses create_all)
- [ ] Authentication & rate limiting
- [ ] Redis job persistence (currently in-memory)
- [ ] Docker containerization

### 🔴 Not Started (Phase 4 Full Scope)

- [ ] Production deployment guide
- [ ] Monitoring & logging (structured logs, metrics)
- [ ] Multi-tenancy
- [ ] OAuth integration
- [ ] WebSocket notifications for real-time updates

---

## 14. Next Steps

After completing setup:

1. **Run the full test suite**:
   ```bash
   pytest tests/ -v --tb=short
   ```

2. **Read the architecture**: See `docs/CURRENT_ARCHITECTURE.md`

3. **Try the UI**: Build a simple pipeline with PM → Backend agents

4. **Explore the API**: Use the interactive docs at http://localhost:8000/docs (Swagger UI)

5. **Contribute**:
   - Fix history UI integration
   - Add template export feature
   - Implement analytics endpoint
   - Write more tests

---

## 15. Support

- **Architecture Docs**: `docs/CURRENT_ARCHITECTURE.md`
- **Phase 4 Plan**: `docs/PHASE4_POLISH_MARKETPLACE_PLAN.md`
- **Implementation Status**: `docs/IMPLEMENTATION_STATUS.md`
- **API Reference**: `docs/PHASE2_API_SUMMARY.md`
- **Issues**: Create issue in GitHub repository

---

**Enjoy building with AI Agent Org! 🚀**
