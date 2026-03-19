"""
Backend Skill: API design pattern detector.
Mirrors skills/security/sast.py exactly — each entry is a named
pattern the BackendAgent pre-scans for locally before calling Claude.
Detects missing patterns (things that should be there but aren't)
and anti-patterns (things that are there but shouldn't be).
"""

# ── Missing-pattern detectors ─────────────────────────────────────────────────
# Applied to SOURCE files — each match means something needs to be added.

API_GAP_PATTERNS: list[dict] = [
    {
        "name": "Route missing response_model",
        "regex": r"@(?:router|app)\.(get|post|put|patch|delete)\s*\([^)]*\)\s*$",
        "severity": "high",
        "category": "contract",
        "description": "FastAPI route without response_model leaks internal fields and breaks OpenAPI docs.",
        "fix": '@router.get("/{id}", response_model=UserResponse)',
        "why": "Prevents accidental exposure of hashed_password, internal flags, etc.",
    },
    {
        "name": "Route missing status_code on POST",
        "regex": r"@(?:router|app)\.post\s*\([^)]*\)\s*$",
        "severity": "medium",
        "category": "contract",
        "description": "POST routes should return 201 Created, not 200 OK.",
        "fix": "@router.post('/', response_model=ItemResponse, status_code=status.HTTP_201_CREATED)",
        "why": "Follows HTTP semantics — clients and caches distinguish 200 vs 201.",
    },
    {
        "name": "Direct db access in route (missing service layer)",
        "regex": r"def \w+\([^)]*db\s*:\s*Session",
        "severity": "high",
        "category": "architecture",
        "description": "Route handler queries DB directly — should delegate to a service/repository.",
        "fix": "Inject UserService via Depends(). Route only validates input and returns response.",
        "why": "Direct DB in routes makes testing require a real DB. Service layer enables unit tests.",
    },
    {
        "name": "Missing pagination on list endpoint",
        "regex": r"@(?:router|app)\.get\s*\(['\"][^'\"]*['\"][^)]*\).*\s*def \w+.*->\s*list",
        "severity": "medium",
        "category": "scalability",
        "description": "List endpoint returns all records — needs skip/limit pagination.",
        "fix": "def list_items(skip: int = 0, limit: int = Query(default=50, le=200)): ...",
        "why": "Returning unbounded lists will OOM at scale and create slow queries.",
    },
    {
        "name": "Missing input validation on body parameter",
        "regex": r"def \w+\([^)]*body\s*:\s*dict[^)]*\)",
        "severity": "high",
        "category": "validation",
        "description": "Route accepts raw dict — should use a typed Pydantic model.",
        "fix": "def create_user(data: UserCreate, ...) — define UserCreate as BaseModel subclass.",
        "why": "Raw dict skips Pydantic validation, OpenAPI generation, and type safety.",
    },
    {
        "name": "Missing rate limiting on auth endpoint",
        "regex": r"@(?:router|app)\.post\s*\(['\"][^'\"]*(?:login|auth|token|register|reset)[^'\"]*['\"]",
        "severity": "high",
        "category": "security",
        "description": "Auth endpoint with no rate limiting — vulnerable to brute force.",
        "fix": "from slowapi import Limiter\n@limiter.limit('5/minute')\nasync def login(..., request: Request): ...",
        "why": "Without rate limiting, attacker can try unlimited password combinations.",
    },
    {
        "name": "Background task not using Celery/queue for long operations",
        "regex": r"background_tasks\.add_task\s*\(\s*(?:send_email|process|generate|export|upload)",
        "severity": "medium",
        "category": "reliability",
        "description": "Long-running operation in BackgroundTask — will fail silently if worker crashes.",
        "fix": "Use Celery + Redis for operations > 2s. BackgroundTask is fire-and-forget with no retry.",
        "why": "FastAPI BackgroundTasks have no persistence — a restart drops queued work.",
    },
    {
        "name": "Missing database index hint",
        "regex": r"filter\s*\(\s*\w+\.\w+\s*==\s*\w+\s*\)(?!.*index)",
        "severity": "medium",
        "category": "performance",
        "description": "Query filters on column with no visible index — may cause full table scan.",
        "fix": "email: Mapped[str] = mapped_column(String(255), unique=True, index=True)",
        "why": "Unindexed filter columns cause O(n) scans — catastrophic at > 10k rows.",
    },
]

# ── Anti-patterns (things that should NOT be there) ───────────────────────────

API_ANTIPATTERN_PATTERNS: list[dict] = [
    {
        "name": "N+1 query in loop",
        "regex": r"for \w+ in \w+:.*\n(?:\s+.*\n)*?\s+db\.(get|query|execute)\s*\(",
        "severity": "critical",
        "category": "performance",
        "description": "Database query inside a loop — classic N+1 problem.",
        "fix": "Use SQLAlchemy joinedload() or selectinload() to fetch related data in one query.",
        "impact": "10 items = 11 queries. 1000 items = 1001 queries. Will kill the DB at scale.",
    },
    {
        "name": "Mutable default argument",
        "regex": r"def \w+\([^)]*=\s*\[\s*\]|def \w+\([^)]*=\s*\{\s*\}",
        "severity": "high",
        "category": "correctness",
        "description": "Mutable default argument shared across all calls — causes subtle state bugs.",
        "fix": "def fn(items: list | None = None):\n    items = items or []",
        "impact": "Second call to fn() sees mutations from the first call.",
    },
    {
        "name": "Exception swallowed with bare except",
        "regex": r"except\s*(?:Exception)?\s*:\s*$",
        "severity": "high",
        "category": "reliability",
        "description": "Exception silently swallowed — failures invisible, debugging impossible.",
        "fix": "except Exception as e:\n    logger.exception('Operation failed')\n    raise HTTPException(500, 'Internal error') from e",
        "impact": "Bugs hide forever. Users see silent failures. On-call gets no alerts.",
    },
    {
        "name": "Blocking I/O in async route",
        "regex": r"async def \w+\([^)]*\).*:\s*\n(?:\s+.*\n)*?\s+(?:time\.sleep|requests\.get|requests\.post)\s*\(",
        "severity": "critical",
        "category": "performance",
        "description": "Synchronous blocking call inside async route — blocks the entire event loop.",
        "fix": "Use httpx.AsyncClient for HTTP, asyncio.sleep for delays, run_in_executor for CPU work.",
        "impact": "One slow request blocks ALL other requests — event loop stalls.",
    },
    {
        "name": "Hardcoded database URL",
        "regex": r"create_engine\s*\(\s*['\"](?!sqlite:///:memory:)[^'\"]+://[^'\"]+['\"]",
        "severity": "critical",
        "category": "security",
        "description": "Database URL hardcoded in source — credentials will be committed to git.",
        "fix": "engine = create_engine(os.environ['DATABASE_URL'])",
        "impact": "Credentials in git = breach. Anyone with repo access has DB access.",
    },
    {
        "name": "Missing transaction rollback on error",
        "regex": r"db\.add\s*\(.*\)\s*\n\s*db\.commit\s*\(\)",
        "severity": "medium",
        "category": "data_integrity",
        "description": "db.commit() without try/except rollback — partial writes on error.",
        "fix": "try:\n    db.add(obj)\n    db.commit()\nexcept Exception:\n    db.rollback()\n    raise",
        "impact": "If commit fails mid-operation, DB is left in inconsistent state.",
    },
    {
        "name": "Using ORM in Alembic migration",
        "regex": r"from models\.\w+ import|from app\.models import",
        "severity": "high",
        "category": "migrations",
        "description": "Importing ORM models in Alembic migration — breaks when model changes later.",
        "fix": "Use op.execute() with raw SQL or op.create_table() with Table() definitions.",
        "impact": "Migration that worked when written will fail after future model changes.",
    },
]

# ── Schema design rules ───────────────────────────────────────────────────────
# Reference data injected into BackendAgent's system prompt.

SCHEMA_DESIGN_RULES: dict[str, dict] = {
    "primary_keys": {
        "rule": "Use UUID string PKs, not auto-increment integers",
        "reason": "Integer IDs are enumerable (attackers can scan /users/1, /users/2...) and don't work with distributed DBs",
        "implementation": "id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))",
    },
    "timestamps": {
        "rule": "Every table gets created_at and updated_at",
        "reason": "Debugging, audit logs, and sync require knowing when rows changed",
        "implementation": "created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())",
    },
    "soft_deletes": {
        "rule": "Use is_deleted flag + deleted_at timestamp, not hard DELETE",
        "reason": "Hard deletes break foreign keys, lose audit trail, and can't be undone",
        "implementation": "is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)\ndeleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)",
    },
    "enums": {
        "rule": "Use Python Enum + SQLAlchemy Enum type for status fields",
        "reason": "String columns allow invalid states; enums enforce valid values at DB level",
        "implementation": "class Status(str, Enum):\n    ACTIVE = 'active'\n    CANCELLED = 'cancelled'\nstatus: Mapped[Status] = mapped_column(Enum(Status), default=Status.ACTIVE)",
    },
    "indexes": {
        "rule": "Index every column used in WHERE, JOIN, or ORDER BY clauses",
        "reason": "Unindexed queries do full table scans — 100ms at 1k rows, 10s at 1M rows",
        "implementation": "__table_args__ = (Index('ix_subscription_user_status', 'user_id', 'status'),)",
    },
    "constraints": {
        "rule": "Add CHECK constraints for business rules that must never be violated",
        "reason": "Application bugs can insert invalid data; DB constraints are the last line of defence",
        "implementation": "CheckConstraint('price >= 0', name='positive_price')",
    },
}

# ── Async patterns ────────────────────────────────────────────────────────────

ASYNC_DB_PATTERNS = """
# Async SQLAlchemy 2.0 — use for high-throughput APIs
# Install: pip install sqlalchemy[asyncio] asyncpg

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

engine = create_async_engine(
    os.environ['DATABASE_URL'].replace('postgresql://', 'postgresql+asyncpg://'),
    pool_size=10, max_overflow=20,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

# Repository — async version
class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: str) -> User | None:
        return await self.db.get(User, user_id)

    async def list(self, skip: int, limit: int) -> tuple[list[User], int]:
        total_q = await self.db.execute(select(func.count()).select_from(User))
        users_q = await self.db.execute(select(User).offset(skip).limit(limit))
        return list(users_q.scalars().all()), total_q.scalar() or 0
"""
