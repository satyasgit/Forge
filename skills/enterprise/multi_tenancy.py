"""
Enterprise skill: Multi-tenancy patterns for SaaS applications.
Covers schema-per-tenant, row-level security (RLS), and database-per-tenant approaches.
"""

MULTI_TENANCY_APPROACHES = {
    "schema_per_tenant": {
        "description": "Separate PostgreSQL schema per tenant (shared database, isolated schemas)",
        "architecture": """
┌─────────────────────────────────────────────┐
│  Shared PostgreSQL Database (mydb)          │
│  ┌──────────────────────────────────────┐ │
│  │ Schema: public (shared tables)       │ │
│  │   • tenants                          │ │
│  │   • users (if shared)                │ │
│  └──────────────────────────────────────┘ │
│  ┌──────────────────────────────────────┐ │
│  │ Schema: tenant_abc                   │ │
│  │   • invoices                        │ │
│  │   • projects                        │ │
│  └──────────────────────────────────────┘ │
│  ┌──────────────────────────────────────┐ │
│  │ Schema: tenant_xyz                   │ │
│  │   • invoices                        │ │
│  │   • projects                        │ │
│  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
""",
        "pros": [
            "Strong data isolation — tenant data in separate schemas",
            "Easy to backup/restore single tenant (pg_dump --schema=tenant_abc)",
            "No query leakage risk (forgetting WHERE tenant_id)",
            "Easy to migrate tenant to separate DB (pg_dump → restore)",
        ],
        "cons": [
            "PostgreSQL limit: ~3000 schemas before planner cache issues",
            "Migrations must run across ALL tenant schemas (N + 1 problem)",
            "Connection pool size × num_schemas can be high",
        ],
        "when_to_use": "SaaS with < 1000 tenants, compliance requires isolation, need per-tenant backups",
        "python_fastapi": '''
# Dynamic schema switching middleware
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    # Extract tenant from subdomain or header
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0]
    tenant = await get_tenant_by_subdomain(subdomain)

    if not tenant or not tenant.is_active:
        return JSONResponse(status_code=404, content={"error": "Tenant not found"})

    # Set tenant context
    request.state.tenant_id = tenant.id
    request.state.tenant_schema = tenant.schema_name

    # Set PostgreSQL search_path for this connection
    if request.url.path.startswith('/api/'):
        # Get DB connection
        async with request.state.db.connection() as conn:
            await conn.execute(
                text(f"SET search_path TO {tenant.schema_name}, public")
            )

    response = await call_next(request)
    return response

# Repository pattern: all queries use tenant schema automatically
async def get_invoices(db: AsyncSession, user_id: str):
    # No WHERE tenant_id needed — schema isolation handles it
    result = await db.execute(
        select(Invoice).where(Invoice.user_id == user_id)
    )
    return result.scalars().all()
''',
        "migration_strategy": '''
# Run migrations across all tenant schemas
# 1. Create new tables in public (shared)
# 2. Loop all tenants: SET search_path, CREATE TABLE ... (inherits from public if needed)

# Or use tools:
# - Alembic with custom env.py that iterates schemas
# - squawk (https://github.com/gordalina/squawk)
# - Custom script:
TENANTS = await db.execute(select(Tenant.schema_name))
for schema in TENANTS:
    await db.execute(text(f"SET search_path TO {schema}"))
    await run_alembic_upgrade()
''',
    },
    "row_level_security": {
        "description": "Single schema + PostgreSQL RLS policies to filter rows by tenant_id",
        "architecture": """
┌─────────────────────────────────────────────┐
│  Shared PostgreSQL Database                 │
│  ┌──────────────────────────────────────┐ │
│  │ Table: invoices                     │ │
│  │   id | tenant_id | amount | ...     │ │
│  └──────────────────────────────────────┘ │
│  RLS Policy: only rows with tenant_id = current_setting('app.current_tenant') visible
└─────────────────────────────────────────────┘
""",
        "pros": [
            "Scales to unlimited tenants (no schema limit)",
            "Single migration target (run once)",
            "Simple queries (no schema switching)",
        ],
        "cons": [
            "Every query must have tenant_id index",
            "Query complexity ↑ (every table joins tenant_id)",
            "Risk of leakage if RLS policy bypassed (bug in app)",
            "All tables must have tenant_id column",
        ],
        "when_to_use": "1000+ tenants, performance critical, disciplined dev team",
        "python_fastapi": '''
# Enable RLS on all tenant tables
async def enable_rls_on_table(table_name: str):
    await db.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))

# Create policy
await db.execute(text('''
    CREATE POLICY tenant_isolation ON invoices
    USING (tenant_id = current_setting('app.current_tenant')::UUID)
'''))

# Set tenant context per request
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    subdomain = request.headers.get("host", "").split(".")[0]
    tenant = await get_tenant_by_subdomain(subdomain)

    if not tenant:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    async with request.state.db.connection() as conn:
        # Set tenant context for this session
        await conn.execute(
            text("SET app.current_tenant = :tid"),
            {"tid": tenant.id}
        )

    response = await call_next(request)
    return response

# All queries now automatically filter by tenant_id:
# SELECT * FROM invoices  → becomes SELECT * FROM invoices WHERE tenant_id = 'abc123'
''',
        "rls_for_all_tables": '''
# Ensure every table has tenant_id
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    amount DECIMAL,
    ...
);

CREATE INDEX idx_invoices_tenant_id ON invoices(tenant_id);
-- RLS policy will use this index efficiently

# Force tenant_id on every table via migration checklist
''',
    },
    "database_per_tenant": {
        "description": "Separate database per tenant (maximum isolation)",
        "architecture": """
┌─────────────┐   ┌─────────────┐
│ Tenant A DB │   │ Tenant B DB │
└─────────────┘   └─────────────┘
       │                 │
       └─────────────────┼─ Connection router
                       │
                 Main App Server
""",
        "pros": [
            "Maximum data isolation",
            "Per-tenant backups/restores (without affecting others)",
            "Can move tenants between servers (sharding)",
            "Compliance-friendly (SOC 2, HIPAA)",
        ],
        "cons": [
            "High infrastructure cost (separate DB instance each)",
            "Complex connection pooling (N databases)",
            "Migrations must run N times (N+1 problem)",
            "Hard to run cross-tenant analytics (no single DB)",
        ],
        "when_to_use": "Enterprise customers with strict compliance needs, banks, healthcare",
        "python_fastapi": '''
# Connection router
class TenantRouter:
    def get_tenant_db_url(self, tenant_id: str) -> str:
        tenant = await db.tenants.get(tenant_id)
        if tenant.database_url:
            return tenant.database_url
        # Or construct from template:
        return f"postgresql://tenant_{tenant_id}@db-host/tenant_{tenant_id}"

    async def get_db(self, tenant_id: str) -> AsyncGenerator[AsyncSession, None]:
        url = self.get_tenant_db_url(tenant_id)
        engine = create_async_engine(url)
        AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        async with AsyncSessionLocal() as session:
            yield session

# Usage in route:
@router.get("/invoices")
async def list_invoices(
    tenant_id: str = Depends(get_tenant_id_from_request),
    db: AsyncSession = Depends(TenantRouter().get_db)
):
    return await db.execute(select(Invoice))
''',
    },
}

CENTRAL_TENANT_MODEL = '''
# shared.tenants table (public schema or separate database)
from sqlalchemy import Column, String, Boolean, Enum
import uuid

class Tenant(Base):
    __tablename__ = 'tenants'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    subdomain = Column(String(50), unique=True, nullable=False)
    plan = Column(Enum('free', 'pro', 'enterprise'), default='free')
    is_active = Column(Boolean, default=True)

    # For schema-per-tenant
    schema_name = Column(String(50), nullable=True)

    # For db-per-tenant
    database_url = Column(String(500), nullable=True)

    # Billing
    stripe_customer_id = Column(String(100), nullable=True)
    subscription_status = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
'''

MIDDLEWARE_AND_AUTH_INTEGRATION = '''
# Tenant identification strategies

# 1. Subdomain (recommended for B2B SaaS)
#   acme.myapp.com → tenant subdomain='acme'
#   Need wildcard DNS (*.myapp.com → your load balancer)

# 2. Custom domain (enterprise)
#   acme-corp.com CNAME → myapp.com
#   Store mapping: tenants table: domain='acme-corp.com'

# 3. Header (for API or mobile)
#   X-Tenant-ID: abc123 (mobile app sends tenant UUID)
#   Verify tenant belongs to authenticated user

# 4. Path-based (simpler but ugly)
#   myapp.com/acme/...  → tenant='acme'

# Middleware that combines all:
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    tenant = None

    # Check header first (mobile/API)
    if 'X-Tenant-ID' in request.headers:
        tenant_id = request.headers['X-Tenant-ID']
        tenant = await get_tenant(tenant_id)

    # Then check subdomain (web)
    elif '.' in request.headers.get('host', ''):
        subdomain = request.headers['host'].split('.')[0]
        tenant = await get_tenant_by_subdomain(subdomain)

    # Fall back to user's default tenant (if logged in)
    elif hasattr(request.state, 'user_id'):
        user = await get_user(request.state.user_id)
        tenant = await get_tenant(user.default_tenant_id)

    if not tenant:
        return JSONResponse(status_code=404, content={"error": "Tenant not found"})

    request.state.tenant = tenant

    # Set appropriate DB/Dynamic schema
    if tenant.database_url:
        request.state.db = get_tenant_db(tenant.database_url)
    elif tenant.schema_name:
        await set_schema(tenant.schema_name)
    else:
        # RLS mode — set session variable
        await set_tenant_context(tenant.id)

    response = await call_next(request)
    return response
'''

DATA_SEEDING_STRATEGIES = {
    "initial_setup": {
        "shared_lookup_tables": """
# countries, currencies, languages — global reference data in public schema
SELECT * FROM public.countries WHERE code = 'US'
""",
        "tenant_defaults": """
# When new tenant signs up:
1. Create tenant record in public.tenants
2. Generate schema name: tenant_{uuid} (or use tenant.id)
3. Run: CREATE SCHEMA {schema_name}
4. Copy initial data: plans, default settings, welcome templates
5. Create admin user for tenant (with reserved subdomain)
6. Create Stripe customer (if billing)
""",
        "blueprint_template": """
# For enterprise: allow customers to template their tenant
template_tenant = get_tenant('blueprint')
pg_dump --schema=tenant_blueprint | psql new_tenant_schema
""",
    },
}

TESTING_MULTI_TENANCY = {
    "unit_tests": "Mock tenant middleware, set request.state.tenant",
    "integration_tests": '''
# Test with real schema switching
async def test_tenant_isolation():
    # Create two tenants
    tenant_a = await create_tenant(name="A", schema="tenant_a")
    tenant_b = await create_tenant(name="B", schema="tenant_b")

    # Create invoice for tenant A
    with schema_context(tenant_a.schema):
        invoice = await create_invoice(amount=100)

    # Verify tenant B cannot see it
    with schema_context(tenant_b.schema):
        result = await db.query(Invoice).first()
        assert result is None
''',
    "factory_pattern": '''
# TenantFactory for tests
class TenantFactory:
    @classmethod
    async def create_tenant_with_data(cls, **kwargs):
        tenant = await Tenant.create(**kwargs)
        await run_migrations(tenant.schema)
        await seed_tenant(tenant)
        return tenant

# In tests:
tenant = await TenantFactory.create_tenant_with_data(
    name="Test Co",
    plan="pro"
)
''',
}

MIGRATION_CHALLENGES_AND_SOLUTIONS = {
    "problem": "Need to add column to invoices table in all tenant schemas (1000 schemas)",
    "naive": "Loop all schemas: ALTER TABLE invoices ADD COLUMN x — takes hours",
    "solution": '''
# Use pg_repack or online schema change tool (pt-online-schema-change equivalent)
# Or: Create new table, copy data in batches, switch using view/rename
# For PostgreSQL: use pg_catalog to generate ALTER for all schemas in single transaction block

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN SELECT schema_name FROM tenants WHERE is_active = true LOOP
    EXECUTE format('ALTER TABLE %I.invoices ADD COLUMN new_field TEXT', r.schema_name);
  END LOOP;
END $$;
''',
    "zero_downtime": "Add nullable column first (fast), backfill in background, add NOT NULL later",
}

SECURITY_MULTI_TENANCY = [
    "✅ NEVER trust client-provided tenant_id — derive from subdomain/header + auth",
    "✅ RLS fallback: ensure query escapes or uses parameterized tenant_id (no SQL injection)",
    "✅ Audit all tenant switching (log tenant context changes)",
    "✅ Row-level security: tenant_id index on EVERY tenant table",
    "✅ Tenant deletion: cascade delete from public.tenants (soft delete flag, not hard)",
    "✅ Cross-tenant query prevention: validate tenant_id in WHERE matches authenticated user",
    "✅ Connection pooling: ensure different tenants don't share connections with stale search_path",
    "✅ Test tenant isolation in staging (copy production tenant to staging, verify no leakage)",
]

PERFORMANCE_TIPS = [
    "Connection pool: create separate pool per schema? Or SET search_path on checkout?",
    "For RLS: create index on (tenant_id, created_at) for common queries",
    "For schema-per-tenant: pg_dump/restore across schemas is faster than cross-db joins",
    "Monitor pg_stat_user_tables — n_tup_ins, n_tup_upd, n_tup_del per schema",
    "Use pg_stat_statements to identify slow queries per tenant (if multi-tenant, anonymize)",
    "Consider Citus (PostgreSQL extension) for automatic sharding by tenant_id",
]

TENANT_SELF_SERVICE = {
    "custom_domain": '''
# Tenant uploads own SSL cert for custom domain
# Or use Let's Encrypt automation (acme.sh) per domain
class DomainManager:
    async def provision_custom_domain(tenant_id: str, domain: str):
        # 1. Verify domain points to your server (TXT record or HTTP challenge)
        # 2. Issue Let's Encrypt certificate
        cert = acme_client.issue_certificate(domain)
        # 3. Configure load balancer/nginx: domain → tenant routing
        # 4. Store cert in database or file system with renewal job
''',
    "onboarding_automation": '''
# New tenant signup flow:
1. Tenant.create(name, subdomain, email)
2. Generate schema (CREATE SCHEMA tenant_xxx) or assign to existing
3. Run migrations (Alembic upgrade head --schema=tenant_xxx)
4. Seed default data: plans, currencies, admin user
5. Send welcome email with instructions
6. (Optional) Clone template tenant data for faster start
''',
}
