"""
QA Skill: pytest pattern library.
Mirrors the structure of skills/security/sast.py — each entry is a named
pattern with a regex detector, severity, description, and a fix template.
The QAAgent runs this locally (no API call) to pre-analyse source code,
identify untested paths, and inject structured findings into the Claude prompt.
"""
from __future__ import annotations

# ── Test-gap patterns ─────────────────────────────────────────────────────────
# Detected in SOURCE code (not test files) — things that need tests written for them.

TEST_GAP_PATTERNS: list[dict] = [
    # FastAPI / Flask routes — every route needs at least one test
    {
        "name": "Untested API route",
        "regex": r"@(?:router|app)\.(get|post|put|patch|delete|head)\s*\(",
        "severity": "high",
        "category": "coverage",
        "description": "API route with no corresponding test detected.",
        "test_types": ["happy_path", "auth_required", "invalid_input", "not_found"],
        "template": "test_{method}_{resource}_{scenario}",
        "example": '''
async def test_get_user_returns_200_for_valid_id(client: AsyncClient, db_user):
    response = await client.get(f"/users/{db_user.id}", headers=auth_headers(db_user))
    assert response.status_code == 200
    assert response.json()["id"] == str(db_user.id)

async def test_get_user_returns_404_for_missing_id(client: AsyncClient, db_user):
    response = await client.get("/users/nonexistent-id", headers=auth_headers(db_user))
    assert response.status_code == 404
''',
    },
    # Pydantic validators / field_validator — needs boundary tests
    {
        "name": "Validator without boundary tests",
        "regex": r"@(?:field_validator|validator)\s*\(",
        "severity": "medium",
        "category": "validation",
        "description": "Pydantic validator found — needs min/max boundary and invalid input tests.",
        "test_types": ["valid_boundary", "invalid_boundary", "edge_case"],
        "template": "test_{model}_{field}_rejects_{invalid_case}",
        "example": '''
def test_user_email_rejects_invalid_format():
    with pytest.raises(ValidationError) as exc:
        UserCreate(email="not-an-email", password="valid123", name="Test")
    assert "email" in str(exc.value)

def test_user_password_rejects_short_value():
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.com", password="short", name="Test")
''',
    },
    # Exception handlers / raise statements — need error path tests
    {
        "name": "Exception path without test",
        "regex": r"\braise\s+(HTTPException|ValueError|PermissionError|NotFoundError)",
        "severity": "high",
        "category": "error_paths",
        "description": "Explicit exception raise found — error path needs a test.",
        "test_types": ["triggers_exception", "correct_status_code", "correct_error_message"],
        "template": "test_{function}_raises_{exception}_when_{condition}",
        "example": '''
async def test_login_returns_401_for_wrong_password(client: AsyncClient):
    response = await client.post("/auth/login", json={
        "email": "user@test.com", "password": "wrong"
    })
    assert response.status_code == 401
    assert "credentials" in response.json()["detail"].lower()
''',
    },
    # Background tasks — need async / side-effect tests
    {
        "name": "Background task without test",
        "regex": r"background_tasks\.add_task\s*\(",
        "severity": "medium",
        "category": "async",
        "description": "BackgroundTask registered — needs test verifying side effect was triggered.",
        "test_types": ["side_effect_called", "side_effect_args"],
        "template": "test_{route}_triggers_{task}_with_{expected_args}",
        "example": '''
async def test_register_sends_welcome_email(client: AsyncClient, mock_send_email):
    await client.post("/auth/register", json=valid_user_payload())
    mock_send_email.assert_called_once()
    assert mock_send_email.call_args[0][0] == valid_user_payload()["email"]
''',
    },
    # DB queries / ORM calls — need isolation via fixtures
    {
        "name": "Database operation needs fixture",
        "regex": r"(?:db|session)\.(?:query|execute|add|delete|get|scalar)\s*\(",
        "severity": "medium",
        "category": "database",
        "description": "Direct DB operation — test must use isolated test DB fixture, not production.",
        "test_types": ["uses_test_db", "rolls_back_on_teardown", "fixture_provides_seed"],
        "template": "test_{repo_method}_with_seeded_{entity}",
        "example": '''
@pytest.fixture
def db_user(db: Session) -> User:
    user = User(email="test@example.com", name="Test User",
                hashed_password=argon2.hash("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()
''',
    },
    # External HTTP calls — must be mocked in unit tests
    {
        "name": "External HTTP call needs mock",
        "regex": r"(?:httpx|requests|aiohttp)\.(get|post|put|patch|delete)\s*\(",
        "severity": "high",
        "category": "mocking",
        "description": "External HTTP call found — must be mocked in unit/integration tests.",
        "test_types": ["mock_success", "mock_failure", "mock_timeout"],
        "template": "test_{function}_handles_{external_service}_{scenario}",
        "example": '''
@pytest.mark.asyncio
async def test_stripe_checkout_handles_api_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("Stripe down"))
    with pytest.raises(HTTPException) as exc:
        await create_checkout_session(user_id="user-1", price_id="price_pro")
    assert exc.value.status_code == 503
''',
    },
    # Auth / permission checks — need both authorised and unauthorised scenarios
    {
        "name": "Auth-gated endpoint needs auth tests",
        "regex": r"Depends\s*\(\s*get_current_user\s*\)",
        "severity": "high",
        "category": "auth",
        "description": "Auth-gated route — needs both authenticated and unauthenticated test cases.",
        "test_types": ["no_token_returns_401", "invalid_token_returns_401", "valid_token_succeeds"],
        "template": "test_{route}_returns_401_without_token",
        "example": '''
async def test_protected_route_returns_401_without_token(client: AsyncClient):
    response = await client.get("/api/me")
    assert response.status_code == 401

async def test_protected_route_returns_401_with_expired_token(client: AsyncClient):
    expired = create_token(user_id="x", kind="access", expires_delta=timedelta(seconds=-1))
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
''',
    },
    # Stripe webhook — must test signature verification
    {
        "name": "Stripe webhook needs signature test",
        "regex": r"stripe\.Webhook\.construct_event\s*\(",
        "severity": "high",
        "category": "webhooks",
        "description": "Stripe webhook handler — needs tests for valid, invalid, and missing signatures.",
        "test_types": ["valid_signature", "invalid_signature_returns_400", "each_event_type"],
        "template": "test_stripe_webhook_{event_type}_handled_correctly",
        "example": '''
def test_stripe_webhook_rejects_invalid_signature(client: TestClient):
    response = client.post("/billing/webhook",
        content=b\'{"type": "checkout.session.completed"}\',
        headers={"stripe-signature": "invalid"})
    assert response.status_code == 400

def test_stripe_webhook_handles_checkout_completed(client: TestClient, stripe_mock):
    payload, sig = build_stripe_event("checkout.session.completed", {"subscription": "sub_123"})
    response = client.post("/billing/webhook", content=payload,
                           headers={"stripe-signature": sig})
    assert response.status_code == 200
''',
    },
    # Pagination — needs limit/offset/empty tests
    {
        "name": "Paginated endpoint needs pagination tests",
        "regex": r"(?:skip|offset|limit|page)\s*[:=]\s*(?:int|0|\d+)",
        "severity": "low",
        "category": "pagination",
        "description": "Pagination params detected — needs tests for first page, empty result, and max limit.",
        "test_types": ["first_page", "second_page", "empty_result", "exceeds_max_limit"],
        "template": "test_{endpoint}_pagination_{scenario}",
        "example": '''
async def test_list_users_returns_first_page(client: AsyncClient, db_users):
    response = await client.get("/users?skip=0&limit=10", headers=admin_headers())
    assert response.status_code == 200
    assert len(response.json()["items"]) <= 10
    assert response.json()["total"] == len(db_users)

async def test_list_users_returns_empty_for_offset_beyond_total(client: AsyncClient):
    response = await client.get("/users?skip=9999&limit=10", headers=admin_headers())
    assert response.json()["items"] == []
''',
    },
]

# ── Anti-patterns in TEST files ───────────────────────────────────────────────
# Detected IN test files — bad practices that weaken the test suite.

TEST_ANTIPATTERN_PATTERNS: list[dict] = [
    {
        "name": "Assert without message on collection",
        "regex": r"assert\s+len\s*\(\w+\)\s*(?:==|>|<)\s*\d+(?!\s*,)",
        "severity": "low",
        "category": "assertions",
        "description": "len() assertion without failure message is hard to debug when it fails.",
        "fix": 'assert len(items) == 3, f"Expected 3 items, got {len(items)}: {items}"',
    },
    {
        "name": "Bare except in test",
        "regex": r"except\s*:",
        "severity": "medium",
        "category": "error_handling",
        "description": "Bare except swallows all errors — tests should only catch specific exceptions.",
        "fix": "with pytest.raises(SpecificException): ...",
    },
    {
        "name": "time.sleep in test",
        "regex": r"time\.sleep\s*\(",
        "severity": "high",
        "category": "performance",
        "description": "time.sleep() makes tests slow and flaky. Use pytest-asyncio, freezegun, or mock timers.",
        "fix": "from freezegun import freeze_time\n@freeze_time('2024-01-01')\ndef test_token_expiry(): ...",
    },
    {
        "name": "Hardcoded test URL",
        "regex": r'https?://(?!localhost|127\.0\.0\.1|testserver)["\']',
        "severity": "medium",
        "category": "isolation",
        "description": "Test calls a real external URL — should use httpx_mock or respx fixture.",
        "fix": "Use httpx_mock.add_response() or @respx.mock to intercept HTTP calls.",
    },
    {
        "name": "Test missing asyncio mark",
        "regex": r"async def test_\w+\s*\([^)]*\)\s*:",
        "severity": "high",
        "category": "async",
        "description": "Async test function missing @pytest.mark.asyncio — test will silently not run.",
        "fix": "@pytest.mark.asyncio\nasync def test_my_function(): ...",
    },
    {
        "name": "Global state mutation in test",
        "regex": r"^\s+\w+\s*=\s*\[\]|^\s+\w+\.clear\(\)",
        "severity": "medium",
        "category": "isolation",
        "description": "Possible global state mutation — tests should be independent and use fixtures.",
        "fix": "Use @pytest.fixture with scope='function' to provide fresh state per test.",
    },
]

# ── Coverage requirements by file type ───────────────────────────────────────

COVERAGE_REQUIREMENTS: dict[str, dict] = {
    "services": {
        "minimum_percent": 90,
        "rationale": "Business logic — every branch must be tested",
        "must_cover": ["happy_path", "validation_errors", "not_found", "permission_denied"],
    },
    "repositories": {
        "minimum_percent": 80,
        "rationale": "DB queries — test with real test DB via fixtures",
        "must_cover": ["create", "read", "update", "delete", "not_found"],
    },
    "routes": {
        "minimum_percent": 85,
        "rationale": "API surface — integration tests with TestClient",
        "must_cover": ["200_ok", "400_bad_input", "401_unauth", "404_not_found", "422_validation"],
    },
    "models": {
        "minimum_percent": 70,
        "rationale": "Validators and computed properties",
        "must_cover": ["valid_input", "invalid_input", "edge_cases"],
    },
    "utils": {
        "minimum_percent": 95,
        "rationale": "Pure functions — fully deterministic, easy to test exhaustively",
        "must_cover": ["all_branches", "boundary_values", "type_errors"],
    },
}
