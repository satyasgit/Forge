"""
Tests for QAAgent.
All tests run without any API call — Claude is fully mocked.
Run: pytest tests/agents/test_qa_agent.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.qa_agent import QAAgent, TestGap, TestAntiPattern


# ── Gap scanner tests (no API calls) ─────────────────────────────────────────

class TestGapScanner:
    def setup_method(self):
        self.agent = QAAgent.__new__(QAAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_unprotected_api_route(self):
        code = {"routes.py": '@router.get("/users/{user_id}")'}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("route" in g.pattern_name.lower() for g in gaps)

    def test_detects_pydantic_validator(self):
        code = {"schemas.py": "@field_validator('email')"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("validator" in g.pattern_name.lower() for g in gaps)

    def test_detects_http_exception_raise(self):
        code = {"service.py": "    raise HTTPException(status_code=404, detail='Not found')"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("exception" in g.pattern_name.lower() for g in gaps)

    def test_detects_background_task(self):
        code = {"routes.py": "background_tasks.add_task(send_email, user.email)"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("background" in g.pattern_name.lower() for g in gaps)

    def test_detects_db_operation(self):
        code = {"repo.py": "return db.query(User).filter(User.id == user_id).first()"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("database" in g.category.lower() or "fixture" in g.pattern_name.lower() for g in gaps)

    def test_detects_external_http_call(self):
        code = {"service.py": "response = httpx.post('https://api.stripe.com/v1/charges', ...)"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("mock" in g.pattern_name.lower() for g in gaps)

    def test_detects_auth_dependency(self):
        code = {"routes.py": "def get_user(current: User = Depends(get_current_user)):"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("auth" in g.category.lower() for g in gaps)

    def test_detects_stripe_webhook(self):
        code = {"billing.py": "event = stripe.Webhook.construct_event(payload, sig, secret)"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any("stripe" in g.pattern_name.lower() or "webhook" in g.pattern_name.lower() for g in gaps)

    def test_skips_test_files(self):
        code = {
            "test_users.py": '@router.post("/users")',
            "conftest.py": "background_tasks.add_task(fn, arg)",
        }
        gaps = self.agent._scan_for_test_gaps(code)
        assert len(gaps) == 0

    def test_gap_has_required_fields(self):
        code = {"routes.py": '@router.get("/items")'}
        gaps = self.agent._scan_for_test_gaps(code)
        assert len(gaps) > 0
        g = gaps[0]
        assert g.severity in ("high", "medium", "low")
        assert g.location.startswith("routes.py:")
        assert len(g.test_types_needed) > 0
        assert g.example

    def test_location_has_correct_line_number(self):
        code = {"routes.py": "# comment\n@router.post('/users')\ndef create(): pass"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert any(":2" in g.location for g in gaps)

    def test_clean_source_has_no_gaps(self):
        # A pure utility function with no DB/HTTP/routes
        code = {"utils.py": "def format_currency(amount: float, currency: str) -> str:\n    return f'{currency}{amount:.2f}'"}
        gaps = self.agent._scan_for_test_gaps(code)
        assert len(gaps) == 0


# ── Anti-pattern scanner tests ────────────────────────────────────────────────

class TestAntiPatternScanner:
    def setup_method(self):
        self.agent = QAAgent.__new__(QAAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_time_sleep(self):
        tests = {"test_users.py": "    time.sleep(2)  # wait for background task"}
        findings = self.agent._scan_existing_tests(tests)
        assert any("sleep" in f.pattern_name.lower() for f in findings)
        assert any(f.severity == "high" for f in findings)

    def test_detects_hardcoded_external_url(self):
        tests = {"test_billing.py": '    response = client.get("https://api.stripe.com/v1/test")'}
        findings = self.agent._scan_existing_tests(tests)
        assert any("url" in f.pattern_name.lower() for f in findings)

    def test_detects_async_test_missing_mark(self):
        tests = {"test_api.py": "async def test_get_user():\n    pass"}
        findings = self.agent._scan_existing_tests(tests)
        assert any("asyncio" in f.pattern_name.lower() for f in findings)

    def test_allows_localhost_urls(self):
        tests = {"test_api.py": '    response = client.get("http://localhost:8000/api/users")'}
        findings = self.agent._scan_existing_tests(tests)
        url_findings = [f for f in findings if "url" in f.pattern_name.lower()]
        assert len(url_findings) == 0

    def test_antipattern_has_fix_suggestion(self):
        tests = {"test_api.py": "    time.sleep(1)"}
        findings = self.agent._scan_existing_tests(tests)
        assert all(f.fix for f in findings)

    def test_clean_test_file_has_no_antipatterns(self):
        tests = {"test_users.py": '''
import pytest
from httpx import AsyncClient

async def test_get_user_returns_200_for_valid_id(client: AsyncClient, db_user):
    response = await client.get(f"/users/{db_user.id}")
    assert response.status_code == 200
'''}
        findings = self.agent._scan_existing_tests(tests)
        # asyncio mark check may flag this — that's fine; other antipatterns should not
        non_async = [f for f in findings if "asyncio" not in f.pattern_name.lower()]
        assert len(non_async) == 0


# ── TestGap dataclass tests ───────────────────────────────────────────────────

class TestGapDataclass:
    def test_to_summary_includes_severity_and_location(self):
        gap = TestGap(
            pattern_name="Untested API route",
            severity="high",
            category="coverage",
            location="routes.py:12",
            evidence="@router.get('/users')",
            test_types_needed=["happy_path", "auth_required"],
            template="test_{method}_{resource}",
            example="def test_get_users_returns_200(): ...",
        )
        summary = gap.to_summary()
        assert "HIGH" in summary
        assert "routes.py:12" in summary
        assert "happy_path" in summary

    def test_to_summary_shows_all_test_types(self):
        gap = TestGap(
            pattern_name="Test", severity="medium", category="auth",
            location="f:1", evidence="code",
            test_types_needed=["no_token_returns_401", "valid_token_succeeds"],
            template="tpl", example="ex",
        )
        assert "no_token_returns_401" in gap.to_summary()
        assert "valid_token_succeeds" in gap.to_summary()


# ── Format methods tests ──────────────────────────────────────────────────────

class TestFormatMethods:
    def setup_method(self):
        self.agent = QAAgent.__new__(QAAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_format_gap_summary_empty(self):
        result = self.agent._format_gap_summary([])
        assert "No" in result

    def test_format_gap_summary_with_items(self):
        gaps = [
            TestGap("Route test", "high", "coverage", "f:1", "code", ["t1"], "tpl", "ex"),
            TestGap("DB fixture", "medium", "database", "f:5", "code", ["t2"], "tpl", "ex"),
        ]
        result = self.agent._format_gap_summary(gaps)
        assert "2 test gaps" in result
        assert "HIGH" in result
        assert "MEDIUM" in result

    def test_format_antipattern_summary_orders_by_severity(self):
        aps = [
            TestAntiPattern("Low issue", "low", "style", "f:3", "code", "fix"),
            TestAntiPattern("High issue", "high", "perf", "f:1", "code", "fix"),
        ]
        result = self.agent._format_antipattern_summary(aps)
        assert result.index("HIGH") < result.index("LOW")


# ── Integration test (mocked API) ─────────────────────────────────────────────

class TestQAAgentIntegration:
    SAMPLE_CODE = {
        "routes/users.py": '''
@router.get("/users/{user_id}")
def get_user(uid: str, _=Depends(get_current_user)):
    raise HTTPException(404, "Not found")
''',
        "services/user.py": '''
def send_notification(user_id: str):
    httpx.post("https://api.slack.com/webhook", json={"text": f"User {user_id} joined"})
''',
    }

    @patch("agents.base.client")
    def test_generate_tests_calls_claude_with_gap_summary(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Test suite here", type="text")]
        mock_response.usage.input_tokens = 1500
        mock_response.usage.output_tokens = 800
        mock_client.messages.create.return_value = mock_response

        agent = QAAgent(project_id=None)
        result = agent.generate_tests(self.SAMPLE_CODE, framework="fastapi")

        assert mock_client.messages.create.called
        call_args = mock_client.messages.create.call_args
        user_content = call_args.kwargs["messages"][0]["content"]

        # Pre-scan findings must be injected
        assert "test gap" in user_content.lower() or "gap" in user_content.lower()
        assert result.output == "Test suite here"

    @patch("agents.base.client")
    def test_generate_tests_includes_antipattern_scan_when_tests_provided(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Tests", type="text")]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_response

        existing = {"test_users.py": "async def test_something():\n    time.sleep(1)"}
        agent = QAAgent(project_id=None)
        agent.generate_tests(self.SAMPLE_CODE, existing_tests=existing)

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "anti-pattern" in user_content.lower() or "antipattern" in user_content.lower()

    @patch("agents.base.client")
    def test_result_tracks_cost(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Tests", type="text")]
        mock_response.usage.input_tokens = 3000
        mock_response.usage.output_tokens = 1500
        mock_client.messages.create.return_value = mock_response

        agent = QAAgent(project_id=None)
        result = agent.generate_tests({"f.py": "code"})

        assert result.input_tokens == 3000
        assert result.output_tokens == 1500
        assert result.cost_usd > 0
        assert result.duration_seconds > 0

    @patch("agents.base.client")
    def test_generate_conftest_passes_models_to_claude(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="conftest here", type="text")]
        mock_response.usage.input_tokens = 400
        mock_response.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_response

        agent = QAAgent(project_id=None)
        agent.generate_conftest(models=["User", "Subscription", "Product"])

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "User" in user_content
        assert "Subscription" in user_content
