"""
Enterprise Full-Stack Development Orchestrator

This meta-skill ties together all layer-specific skills and provides
architectural decision guidance for full-stack application development.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Architecture Decision Matrix
# ─────────────────────────────────────────────────────────────────────────────

ARCHITECTURE_DECISION_MATRIX = """
## Stack Selection Guide

### Frontend Decision Tree
Q: Do you need SSR/SEO?
├─ Yes → Next.js (React) or Nuxt (Vue)
└─ No →
    ├─ Mobile-first PWA → React Native Web or Flutter Web
    ├─ Admin dashboards → React + shadcn/ui or Vue + Headless UI
    └─ Simple marketing site → SvelteKit or Astro

Q: Team expertise?
├─ React/TS → React ecosystem (clients expect it)
├─ Vue → Vue 3 + Composition API + Pinia
├─ Flutter → Flutter web + mobile (single codebase)
└─ None → React (largest talent pool, most resources)

### Backend Decision Tree
Q: Throughput requirements?
├─ High (>10k RPS) → Go + Gin/Fiber or Rust
├─ Medium (1-10k RPS) → FastAPI (Python async) or Node.js
├─ Low (<1k RPS) → Any (choose based on team)
└─ Data-heavy ML → Python + FastAPI

Q: Real-time features needed?
├─ Heavy (chat, collaboration) → Node.js + Socket.io
├─ Moderate (notifications) → FastAPI + WebSockets or SSE
└─ None → REST is fine

Q: Existing ecosystem?
├─ Python ML stack → FastAPI (reuse models)
├─ Node.js microservices → NestJS (maintain consistency)
├─ Enterprise Java → Stay in JVM (Spring Boot)
└─ New project → FastAPI (best DX) or Node (most portable)

---

## Layered Architecture (Clean/Onion)

Every project should follow this structure regardless of stack:

```
src/
├── presentation/      # UI layer: React components, SwiftUI views, Flutter widgets
│   └── components/    # Reusable UI primitives (button, modal, table)
│
├── application/       # Use cases: orchestrates domain objects
│   ├── services/      # Application services (orchestration)
│   ├── dtos/          # Data transfer objects (API contracts)
│   └── exceptions.py  # Domain exceptions (UserNotFoundError, etc.)
│
├── domain/            # Business logic: entities, value objects, aggregates
│   ├── models/        # Core business objects (User, Invoice, Subscription)
│   ├── repositories/  # Interfaces (abstract), not implementations
│   ├── value_objects/ # Email, Money, UserId (validated)
│   └── events/        # Domain events (UserCreated, PaymentSucceeded)
│
├── infrastructure/    # External concerns: DB, HTTP, file storage, email
│   ├── persistence/   # ORM models, migrations, repositories impl
│   ├── http/          # Controllers, routers, middleware
│   ├── external/      # API clients (Stripe, SendGrid, etc.)
│   └── config.py      # Environment variables, settings
│
└── shared/            # Common utilities: logging, errors, helpers
```

**Dependency rule**: presentation → application → domain ← infrastructure
Never: domain imports infrastructure

---

## API Design Standards

### RESTful JSON
```
# Resource naming: plural nouns
GET    /api/v1/users          # list
POST   /api/v1/users          # create
GET    /api/v1/users/{id}     # get
PATCH  /api/v1/users/{id}     # update (partial)
PUT    /api/v1/users/{id}     # replace (full)
DELETE /api/v1/users/{id}     # delete

# Response format (consistent across all endpoints)
{
  "data": {...},         # Resource or array on list
  "meta": {              # Pagination, rate limits
    "page": 1,
    "per_page": 50,
    "total": 1234
  }
}

# Error format
{
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User with id '123' does not exist",
    "details": {"field": "email", "issue": "already exists"}
  }
}
```

### GraphQL (alternative for complex UIs)
```graphql
type Query {
  user(id: UUID!): User
  users(filter: UserFilter, pagination: Page): [User!]!
}

type Mutation {
  createUser(input: CreateUserInput!): CreateUserResult!
}

# Use DataLoader to batch & cache N+1 queries
# Use persisted queries (SHA hash) in production for security + caching
```

---

## Cross-Cutting Concerns

### Authentication & Authorization
- **Auth**: JWT short-lived access tokens (15min) + refresh tokens (7d, httpOnly cookie)
- **RBAC**: roles table + user_role join, check in middleware/decorator
- **ABAC**: attribute-based for fine-grained (tenant_id + role + feature flags)
- **SSO**: SAML 2.0 or OIDC for enterprise

### Observability
- **Logging**: Structured JSON logs with trace_id, include: timestamp, level, service, user_id, correlation_id
- **Metrics**: Prometheus format at /metrics: counters, histograms, gauges
- **Tracing**: OpenTelemetry distributed traces, export to Jaeger or commercial APM
- **Errors**: Sentry with PII scrubbing, set environment + release

### Data Protection
- **Encryption**: TLS 1.3 in transit, AES-256 at rest (DB encryption, S3 SSE-KMS)
- **PII**: Tokenize or hash where possible, encrypt at application layer for extra-sensitive
- **Backups**: Daily full + hourly incremental, encrypted, test restore monthly
- **Retention**: Define schedule per data type (logs 90d, audit logs 7y, soft-deleted users 30d)

### Scalability
- **Vertical**: Optimize query, add indices, cache
- **Horizontal**: Stateless app servers behind load balancer, sticky sessions for WebSocket
- **Database**: Read replicas for queries, sharding for >100M rows
- **Async**: Queue non-critical work (email, webhooks) via Redis/Celery/Bull

---

## Integration Contracts

### Event-Driven Communication
```python
# Producer
await redis.xadd('user.created', {
    'user_id': user.id,
    'event_type': 'user.created',
    'timestamp': now_iso(),
    'data': json.dumps(user.to_dict())
})

# Consumer (idempotent, replayable)
while True:
    messages = await redis.xread({'user.created': last_id}, count=10)
    for msg_id, msg in messages:
        await handle_user_created(msg)
        await redis.xack('user.created', 'consumer-group', msg_id)
```

### Webhook Security
```
# Outgoing webhooks: sign with HMAC
signature = hmac.new(secret, payload, sha256).hexdigest()
headers['X-Webhook-Signature'] = signature

# Incoming webhooks: verify signature
expected = hmac.new(secret, payload, sha256).hexdigest()
if not constant_time_compare(request.headers['X-Webhook-Signature'], expected):
    raise HTTPException(400, 'Invalid signature')
```

---

## Deployment Checklist

**Before pushing to production:**

- [ ] All environment variables defined (no hardcoded passwords)
- [ ] Database migrations tested locally + on staging
- [ ] Health check endpoints /health and /ready responding
- [ ] Metrics endpoint /metrics exposing Prometheus metrics
- [ ] Structured logging (JSON) with correlation_id
- [ ] Rate limiting on all public endpoints (100req/min per IP)
- [ ] CORS configured with specific allowlist (not '*')
- [ ] Secrets scanned (GitGuardian, trufflehog)
- [ ] Dependency vulnerabilities scanned (snyk, dependabot)
- [ ] Tests passing (unit + integration) with coverage >70%
- [ ] Load test: p99 latency < 200ms for critical paths
- [ ] Backup/restore procedure documented and tested
- [ ] Incident response runbook: who to page, how to rollback, how to restore DB
- [ ] Feature flags for risky changes (enable/disable without deploy)
- [ ] Monitoring dashboards (errors, latency, throughput) created
- [ ] Alerting rules configured (error rate, latency, disk space)
- [ ] SSL certificate valid (auto-renew via Let's Encrypt or managed cert)

---

## Stack-Specific Implementation Guides

For each supported stack (React, Vue, Flutter, FastAPI, Node/Nest, React Native, Swift, Kotlin),
refer to the skill files in the same directory for:

- **Component templates** (start from this structure)
- **State management patterns** (React Query, Riverpod, Pinia, etc.)
- **Routing conventions** (Expo Router, React Router, Vue Router)
- **Testing templates** (Vitest, Jest, pytest, XCTest, Espresso)
- **Build & deployment** (Dockerfile, CI/CD templates, app store submission)
"""
