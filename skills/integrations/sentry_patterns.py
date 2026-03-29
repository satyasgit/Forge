"""
Integration skill: Sentry error tracking and performance monitoring.
Covers initialization, breadcrumbs, custom contexts, performance tracing, and alerting.
"""

SENTRY_INITIALIZATION = '''
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

def filter_sensitive_data(event, hint):
    """Remove PII and secrets from Sentry events."""
    # Remove request data
    if 'request' in event:
        event['request'].pop('cookies', None)
        event['request'].pop('data', None)
        event['request'].pop('query_string', None)

    # Remove environment variables from extra
    if 'extra' in event:
        event['extra'].pop('password', None)
        event['extra'].pop('api_key', None)
        event['extra'].pop('secret', None)

    # Scrub stacktrace local variables
    if 'exception' in event and 'values' in event['exception']:
        for exc in event['exception']['values']:
            if 'stacktrace' in exc and 'frames' in exc['stacktrace']:
                for frame in exc['stacktrace']['frames']:
                    frame['vars'] = {}  # Clear all locals

    return event

sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    environment=os.getenv('ENVIRONMENT', 'production'),  # production, staging, development
    release=f"myapp@{os.getenv('GIT_SHA', 'dev')}",  # Git commit SHA
    dist=os.getenv('GIT_BRANCH', 'main'),  # Branch/tag
    traces_sample_rate=1.0 if os.getenv('ENVIRONMENT') == 'development' else 0.1,
    # 100% in dev for testing, 10% in prod for APM (cost control)
    profiles_sample_rate=1.0 if os.getenv('ENVIRONMENT') == 'development' else 0.1,
    # CPU profiling for performance analysis

    integrations=[
        FastApiIntegration(),
        SqlalchemyIntegration(),
        RedisIntegration(),
        CeleryIntegration(),
        LoggingIntegration(
            level=logging.INFO,  # Capture INFO and above as breadcrumbs
            event_level=logging.ERROR  # Send ERROR+ as events
        ),
    ],
    before_send=filter_sensitive_data,
    before_send_transaction=filter_sensitive_data,

    # Attach Git metadata for source map deobfuscation
    include_source_context=True,
    include_local_variables=True,

    # Debug mode (development only)
    debug=os.getenv('ENVIRONMENT') == 'development',
)

# Set user context for authenticated requests
@app.middleware("http")
async def set_sentry_user(request: Request, call_next):
    if hasattr(request.state, "user_id"):
        sentry_sdk.set_user({
            "id": request.state.user_id,
            "email": getattr(request.state, "user_email", None),
            "ip_address": request.client.host,
        })
    response = await call_next(request)
    return response
'''

SENTRY_PERFORMANCE_MONITORING = '''
# Auto-instrumented (via integrations):
# - HTTP requests (incoming FastAPI, outgoing httpx)
# - Database queries (SQLAlchemy, asyncpg)
# - Redis operations (redis-py)
# - Template rendering (Jinja2)

# Manual spans for custom business logic:
import sentry_sdk
from sentry_sdk import start_transaction, start_span

# Transaction (entire request)
@start_transaction(name="process_checkout", op="http.server")
async def process_checkout(request):
    # Transaction auto-started by FastAPI integration
    # Add custom tags/context:
    sentry_sdk.set_tag("checkout_type", "subscription")
    sentry_sdk.set_context("checkout", {
        "user_id": user_id,
        "cart_items": len(items),
        "total": str(total),
    })

    # Span (sub-operation)
    with start_span(op="payment", description="Charge credit card"):
        await payment_service.charge(stripe_token, amount)

    with start_span(op="database", description="update inventory"):
        await inventory_service.reserve(items)

    return {"status": "success"}

# Nested spans for complex operations:
with sentry_sdk.start_span(op="task", description="generate_report"):
    with sentry_sdk.start_span(op="database", description="fetch_transactions"):
        transactions = await db.fetch_transactions(...)

    with sentry_sdk.start_span(op="pdf", description="render_pdf"):
        pdf = await renderer.generate(transactions)

    with sentry_sdk.start_span(op="storage", description="upload_s3"):
        await s3.upload(pdf, key)
'''

SENTRY_BREADCRUMBS = '''
# Breadcrumbs: trail of events leading to error (context for debugging)
# Captured automatically by integrations, manually added for custom events

import sentry_sdk

# Manual breadcrumb
sentry_sdk.add_breadcrumb(
    category="auth",
    message="User failed to login",
    level="warning",
    data={
        "email": user_email,
        "attempt": login_attempt,
    }
)

# HTTP request automatically logged as breadcrumb
# (enabled by default in FastApiIntegration)

# User action breadcrumb (for UI flows)
def on_button_click(action: str):
    sentry_sdk.add_breadcrumb(
        category="ui",
        message=f"User clicked: {action}",
        level="info",
    )

# Breadcrumb types:
# - navigation: page changes
# - http: API calls
# - ui: user interactions
# - auth: login/logout
# - database: queries (but SQL already instrumented)
# - custom: anything else
'''

SENTRY_ALERT_RULES = {
    "error_rate": {
        "condition": "times(transaction, status:error) / count(transaction) > 0.02",
        "threshold": "> 2% error rate over 5 minutes",
        "action": "Notify #devops Slack channel, page on-call if critical",
    },
    "new_errors": {
        "condition": "NEW(template) OR SPONTANEOUS_RISE(users())",
        "threshold": "New error fingerprint appears",
        "action": "Alert engineering team immediately (P1)",
    },
    "performance": {
        "condition": "p95(duration) > 2.0 AND percentage(times(transaction, status:ok)) < 0.9",
        "threshold": "p95 latency > 2s (baseline is 500ms)",
        "action": "Create ticket, investigate DB queries or N+1",
    },
    "throughput_drop": {
        "condition": "count() < baseline * 0.5",
        "threshold": "Request volume drops 50% (site likely down)",
        "action": "Page on-call immediately (P0)",
    },
    "specific_exception": {
        "condition": "exception:PaymentProcessingError",
        "threshold": "Any occurrence",
        "action": "Notify billing team Slack",
    },
}

SENTRY_TAGS_AND_CONTEXTS = '''
# Use tags for filtering and grouping
sentry_sdk.set_tag("feature", "checkout")
sentry_sdk.set_tag("browser", "Chrome")
sentry_sdk.set_tag("user_tier", "pro")

# Contexts: structured additional data (not used for grouping)
sentry_sdk.set_context("user", {
    "id": user.id,
    "plan": user.plan,
    "created_at": user.created_at.isoformat(),
})
sentry_sdk.set_context("payment", {
    "gateway": "stripe",
    "amount": amount,
    "currency": "usd",
})

# Environment-specific tags automatically added:
# environment, release, platform, sdk.name, sdk.version
'''

SENTRY_REPLAY_CONFIG = '''
# Session replay: capture user interactions to reproduce bugs
sentry_sdk.init(
    ...,
    # Enable replays
    enable_tracing=True,  # Required for replays
    replays_session_sample_rate=0.1,  # 10% of sessions
    replays_on_error_sample_rate=1.0,  # 100% of error sessions

    # Privacy:
    # mask_all_inputs=True  # Redact all text inputs
    # block_all_images=True  # Don't capture images (PII)
)

# Replay sampling: capture all errors + 10% of sessions
# Users can opt-out via sentryOptOut=true query param
'''

SENTRY_RELEASE_TRACKING = '''
# Associate errors with specific releases (Git commit)
sentry_sdk.init(
    release=os.getenv('GIT_SHA'),  # Full SHA or semver: myapp@1.2.3
    dist=os.getenv('GIT_BRANCH'),  # Branch name
)

# In production deploy script:
# 1. Set GIT_SHA env var (use `git rev-parse HEAD`)
# 2. Tell Sentry about new release (CLI):
#    sentry-cli releases new myapp@${GIT_SHA}
#    sentry-cli releases files ${GIT_SHA} upload-sourcemaps ./dist
#    sentry-cli releases finalize ${GIT_SHA}
# 3. Deploy app with GIT_SHA env

# Benefits: see which users affected, track regressions, source maps for JS stacktraces
'''

SENTRY_MONITORING_DASHBOARD = {
    "overview": [
        "Events received (last 24h)",
        "Error rate trend (last 7d)",
        "Top 5 error types",
        "Latest release errors",
    ],
    "performance": [
        "p50/p95/p99 LCP (largest contentful paint)",
        "Apdex score (0-1, higher is better)",
        "Slowest transactions (by p95)",
        "Regressed transactions (vs last week)",
    ],
    "replays": [
        "Sessions with rage clicks",
        "Sessions ending with error",
        "Replay duration histogram",
    ],
    "release_health": [
        "Crash-free users (%)",
        "Crash-free sessions (%)",
        "Adoption rate by version",
    ],
}

SENTRY_SDK_BY_LANGUAGE = {
    "python": {
        "integrations": [
            "asyncio (async/await)",
            "aiohttp (async HTTP)",
            "boto3 (AWS)",
            "celery (task queues)",
            "django (web framework)",
            "fastapi (web framework)",
            "flask (web framework)",
            "sqlalchemy (database)",
            "redis (cache)",
        ],
        "config": "sentry_sdk.init(dsn, integrations=[...])",
    },
    "node": {
        "integrations": [
            "express (web)",
            "koa (web)",
            "nest (web)",
            "mongodb",
            "postgres",
            "redis",
            "bullmq (queues)",
        ],
        "config": "Sentry.init({ dsn, integrations: [...] })",
    },
    "react": {
        "integrations": [
            "React error boundary",
            "React Query (if used)",
        ],
        "config": "Sentry.init({ dsn, integrations: [new BrowserTracing()] })",
        "frontend_errors": "Capture unhandled exceptions, unhandled promise rejections",
    },
}

SENTRY_SAMPLE_RATE_CALCULATION = '''
# Monthly cost = (events captured per month) × (price per event)

# Events: errors + transactions (APM)
# FastAPI app: ~10k errors/month (rare), ~10M transactions/month

# Cost optimization:
# - Set traces_sample_rate to 0.1 (10% of transactions) for APM
# - Errors are always captured (100%)
# - For high-volume: use traces_sampler to sample only slow transactions

def traces_sampler(sampling_context):
    # Sample only slow transactions (p95 > 1s)
    if sampling_context['parent_span'] and sampling_context['parent_span']['description']:
        if sampling_context['parent_span']['description'].startswith('db.'):
            return 0.5  # Sample 50% of DB queries
    return 0.1  # Default 10%

sentry_sdk.init(
    traces_sampler=traces_sampler,
    traces_sample_rate=1.0,  # Override by sampler
)
'''

SENTRY_ANTI_PATTERNS = [
    "❌ Logging same error twice (Sentry + logs) — noise",
    "❌ Not filtering PII — GDPR violation",
    "❌ Disabling source maps in production — useless stacktraces",
    "❌ 100% traces_sample_rate at scale → $$$$ cost",
    "❌ No alert rules — errors ignored until users complain",
    "❌ Ignoring DLQ/failed jobs → tasks silently lost",
    "❌ Using Sentry as logging (breadcrumbs for normal flow)",
    "❌ Not setting release → can't track regressions",
    "❌ Capturing large payloads (request bodies) in events — memory blowup",
    "❌ Sentry down → throwing exceptions (wrap init in try/except)",
]
