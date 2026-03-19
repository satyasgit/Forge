"""
QA Skill: fixture library.
Mirrors skills/security/threat_model.py — structured templates injected
verbatim into the QAAgent's Claude prompt so it produces correct pytest
fixtures every time, without hallucinating syntax.
"""

# ── Core conftest.py injected into every project ─────────────────────────────

CONFTEST_TEMPLATE = '''
# tests/conftest.py — project-wide fixtures

import asyncio
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from core.database import Base, get_db

# ── Event loop ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ── Test database (in-memory SQLite, isolated per test) ──────────────────────

@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

# ── Async HTTP client ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db: Session) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the FastAPI app with test DB injected."""
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.clear()

# ── Auth helpers ──────────────────────────────────────────────────────────────

@pytest.fixture
def db_user(db: Session):
    from models.user import User
    from passlib.hash import argon2
    user = User(
        id="test-user-id",
        email="test@example.com",
        name="Test User",
        hashed_password=argon2.hash("password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()

@pytest.fixture
def db_admin(db: Session):
    from models.user import User
    from passlib.hash import argon2
    admin = User(
        id="admin-user-id",
        email="admin@example.com",
        name="Admin User",
        hashed_password=argon2.hash("adminpass123"),
        is_active=True,
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    yield admin
    db.delete(admin)
    db.commit()

def auth_headers(user) -> dict[str, str]:
    from core.auth import create_token
    token = create_token(user_id=str(user.id), kind="access")
    return {"Authorization": f"Bearer {token}"}

def admin_headers(admin) -> dict[str, str]:
    return auth_headers(admin)
'''

# ── Stripe test helpers ───────────────────────────────────────────────────────

STRIPE_FIXTURES = '''
# tests/fixtures/stripe_fixtures.py

import json
import time
import stripe
import pytest

STRIPE_TEST_WEBHOOK_SECRET = "whsec_test_secret"

def build_stripe_event(event_type: str, data: dict) -> tuple[bytes, str]:
    """Build a signed Stripe webhook payload for testing."""
    payload = json.dumps({
        "type": event_type,
        "data": {"object": data},
        "id": f"evt_test_{event_type.replace(\'.\', \'_\')}",
    }).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}"
    import hmac, hashlib
    secret = STRIPE_TEST_WEBHOOK_SECRET.replace("whsec_", "")
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    return payload, header

@pytest.fixture
def stripe_mock(monkeypatch):
    """Mock all Stripe API calls. Returns a dict of call recorders."""
    calls = {"checkout": [], "subscriptions": [], "customers": []}

    class FakeSession:
        url = "https://checkout.stripe.com/test-session"
        id = "cs_test_123"

    class FakeCustomer:
        id = "cus_test_123"

    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: FakeSession())
    monkeypatch.setattr(stripe.Customer, "create", lambda **kw: FakeCustomer())
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: {
        "id": sid, "status": "active", "customer": "cus_test_123",
        "current_period_end": int(time.time()) + 2592000,
        "trial_end": None,
        "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
    })
    return calls
'''

# ── Pytest configuration ──────────────────────────────────────────────────────

PYTEST_INI = '''
# pytest.ini (or pyproject.toml [tool.pytest.ini_options])

[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    -p no:warnings
markers =
    unit: Pure unit tests — no I/O, no DB, no HTTP
    integration: Tests with real DB (test SQLite)
    e2e: Full stack tests with real HTTP client
    slow: Tests taking > 1s
'''

# ── Test naming conventions ───────────────────────────────────────────────────

TEST_NAMING_RULES = {
    "pattern": "test_{unit}_{scenario}_{expected_outcome}",
    "examples": [
        "test_login_with_wrong_password_returns_401",
        "test_create_user_with_duplicate_email_raises_conflict",
        "test_get_users_without_auth_returns_401",
        "test_stripe_webhook_with_invalid_signature_returns_400",
        "test_subscription_upgrade_updates_entitlements",
    ],
    "anti_examples": [
        "test_login",          # too vague — what scenario? what outcome?
        "test1",               # meaningless
        "test_it_works",       # not specific
        "TestLogin.test",      # class-based — avoid unless parameterised
    ],
}

# ── Load test template (Locust) ───────────────────────────────────────────────

LOCUST_TEMPLATE = '''
# tests/load/locustfile.py
from locust import HttpUser, task, between

class AppUser(HttpUser):
    wait_time = between(1, 3)
    token: str = ""

    def on_start(self):
        """Login and cache token before running tasks."""
        res = self.client.post("/auth/login", json={
            "email": "loadtest@example.com",
            "password": "loadtest123",
        })
        self.token = res.json().get("access_token", "")

    @task(3)
    def get_profile(self):
        self.client.get("/api/me", headers={"Authorization": f"Bearer {self.token}"})

    @task(2)
    def list_items(self):
        self.client.get("/api/items?limit=10", headers={"Authorization": f"Bearer {self.token}"})

    @task(1)
    def create_item(self):
        self.client.post(
            "/api/items",
            json={"name": "Load test item", "description": "Created by Locust"},
            headers={"Authorization": f"Bearer {self.token}"},
        )

# Run: locust -f tests/load/locustfile.py --host=http://localhost:8000
# Targets: p95 < 200ms on GET /api/me at 100 concurrent users
'''
