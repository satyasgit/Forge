"""
Tests for BackendAgent, CodeReviewAgent, and DevOpsAgent.
All tests run without any API call — Claude is fully mocked.
Run: pytest tests/agents/test_backend_code_review_devops.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.backend_agent import BackendAgent, APIGap, APIAntiPattern
from agents.code_review_agent import CodeReviewAgent, CodeSmell
from agents.devops_agent import DevOpsAgent, InfraIssue


# ════════════════════════════════════════════════════════════════════════════════
# BackendAgent
# ════════════════════════════════════════════════════════════════════════════════

class TestBackendAPIGapScanner:
    def setup_method(self):
        self.agent = BackendAgent.__new__(BackendAgent)
        self.agent.project_id = self.agent.memory = None
        self.agent._messages = []

    def test_detects_route_missing_response_model(self):
        code = {"routes.py": '@router.get("/users")\ndef list_users(): pass'}
        gaps = self.agent._scan_for_api_gaps(code)
        assert any("response_model" in g.pattern_name.lower() for g in gaps)

    def test_detects_post_missing_201(self):
        code = {"routes.py": '@router.post("/users")\ndef create(): pass'}
        gaps = self.agent._scan_for_api_gaps(code)
        assert any("201" in g.pattern_name or "status_code" in g.pattern_name.lower() for g in gaps)

    def test_detects_raw_dict_body(self):
        code = {"routes.py": "def create_user(body: dict, db=Depends(get_db)): pass"}
        gaps = self.agent._scan_for_api_gaps(code)
        assert any("dict" in g.pattern_name.lower() or "validation" in g.pattern_name.lower() for g in gaps)

    def test_detects_auth_endpoint_missing_rate_limit(self):
        code = {"routes.py": '@router.post("/auth/login")\ndef login(data: dict): pass'}
        gaps = self.agent._scan_for_api_gaps(code)
        assert any("rate" in g.pattern_name.lower() or "limit" in g.pattern_name.lower() for g in gaps)

    def test_skips_non_python_files(self):
        code = {"config.yml": '@router.post("/login")\ndef login(): pass'}
        gaps = self.agent._scan_for_api_gaps(code)
        assert len(gaps) == 0


class TestBackendAntiPatternScanner:
    def setup_method(self):
        self.agent = BackendAgent.__new__(BackendAgent)
        self.agent.project_id = self.agent.memory = None
        self.agent._messages = []

    def test_detects_bare_except_pass(self):
        code = {"service.py": "try:\n    do_thing()\nexcept:\n    pass"}
        aps = self.agent._scan_for_antipatterns(code)
        assert any("except" in a.pattern_name.lower() for a in aps)

    def test_detects_hardcoded_db_url(self):
        code = {"db.py": 'engine = create_engine("postgresql://user:pass@localhost/db")'}
        aps = self.agent._scan_for_antipatterns(code)
        assert any("database" in a.pattern_name.lower() or "url" in a.pattern_name.lower() for a in aps)

    def test_detects_mutable_default_list(self):
        code = {"utils.py": "def process(items=[]):\n    pass"}
        aps = self.agent._scan_for_antipatterns(code)
        assert any("mutable" in a.pattern_name.lower() for a in aps)

    def test_detects_mutable_default_dict(self):
        code = {"utils.py": "def fn(config={}):\n    pass"}
        aps = self.agent._scan_for_antipatterns(code)
        assert any("mutable" in a.pattern_name.lower() for a in aps)

    def test_clean_code_has_no_antipatterns(self):
        code = {"service.py": '''
def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)
'''}
        aps = self.agent._scan_for_antipatterns(code)
        assert len(aps) == 0


class TestAPIGapDataclass:
    def test_to_summary_has_severity_and_location(self):
        g = APIGap("Missing response_model", "high", "contract", "routes.py:5", "@router.get", "fix", "why")
        assert "HIGH" in g.to_summary()
        assert "routes.py:5" in g.to_summary()
        assert "contract" in g.to_summary()


class TestBackendIntegration:
    @patch("agents.base.client")
    def test_build_feature_injects_gap_summary(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Backend code here")
        agent = BackendAgent(project_id=None)
        result = agent.build_feature(
            "User management API",
            existing_code={"routes.py": '@router.post("/users")\ndef create(body: dict): pass'},
        )
        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "gap" in user_content.lower() or "anti-pattern" in user_content.lower()
        assert result.output == "Backend code here"

    @patch("agents.base.client")
    def test_design_schema_passes_entities(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Schema")
        agent = BackendAgent(project_id=None)
        agent.design_schema(["User", "Subscription", "Invoice"])
        content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "User" in content and "Subscription" in content


# ════════════════════════════════════════════════════════════════════════════════
# CodeReviewAgent
# ════════════════════════════════════════════════════════════════════════════════

class TestCodeSmellScanner:
    def setup_method(self):
        self.agent = CodeReviewAgent.__new__(CodeReviewAgent)
        self.agent.project_id = self.agent.memory = None
        self.agent._messages = []

    def test_detects_print_statement(self):
        code = {"service.py": '    print("User logged in:", user_id)'}
        smells = self.agent._scan_for_smells(code)
        assert any("print" in s.pattern_name.lower() for s in smells)

    def test_detects_assert_for_runtime(self):
        code = {"service.py": "    assert user_id is not None"}
        smells = self.agent._scan_for_smells(code)
        assert any("assert" in s.pattern_name.lower() for s in smells)

    def test_detects_star_import(self):
        code = {"routes.py": "from models import *"}
        smells = self.agent._scan_for_smells(code)
        assert any("star" in s.pattern_name.lower() or "import" in s.pattern_name.lower() for s in smells)

    def test_detects_none_comparison_with_equality(self):
        code = {"service.py": "    if user == None:"}
        smells = self.agent._scan_for_smells(code)
        assert any("none" in s.pattern_name.lower() for s in smells)

    def test_detects_todo_comment(self):
        code = {"routes.py": "    # TODO: add input validation"}
        smells = self.agent._scan_for_smells(code)
        assert any("todo" in s.pattern_name.lower() or "fixme" in s.pattern_name.lower() for s in smells)

    def test_detects_typescript_any(self):
        code = {"api.ts": "const handler = (data: any) => data.value"}
        smells = self.agent._scan_for_smells(code)
        assert any("any" in s.pattern_name.lower() for s in smells)

    def test_detects_console_log(self):
        code = {"utils.ts": "    console.log('Processing:', userId)"}
        smells = self.agent._scan_for_smells(code)
        assert any("console" in s.pattern_name.lower() for s in smells)

    def test_detects_non_null_assertion(self):
        code = {"component.tsx": "    const name = user!.name"}
        smells = self.agent._scan_for_smells(code)
        assert any("null" in s.pattern_name.lower() or "!" in s.pattern_name for s in smells)

    def test_skips_comment_lines(self):
        code = {"utils.py": "# print('this is in a comment')"}
        smells = self.agent._scan_for_smells(code)
        print_smells = [s for s in smells if "print" in s.pattern_name.lower()]
        assert len(print_smells) == 0

    def test_smell_has_required_fields(self):
        code = {"service.py": "    assert user is not None"}
        smells = self.agent._scan_for_smells(code)
        if smells:
            s = smells[0]
            assert s.severity in ("critical", "high", "medium", "low")
            assert "service.py:" in s.location
            assert s.fix

    def test_clean_code_has_no_smells(self):
        code = {"service.py": '''
import logging
logger = logging.getLogger(__name__)

def get_user_by_email(db: Session, email: str) -> User | None:
    if email is None:
        raise ValueError("Email is required")
    return db.scalar(select(User).where(User.email == email))
'''}
        smells = self.agent._scan_for_smells(code)
        critical_high = [s for s in smells if s.severity in ("critical", "high")]
        assert len(critical_high) == 0


class TestCodeSmellDataclass:
    def test_to_summary_format(self):
        s = CodeSmell("Print statement", "medium", "observability", "service.py:12", "print('x')", "use logging")
        assert "MEDIUM" in s.to_summary()
        assert "service.py:12" in s.to_summary()
        assert "observability" in s.to_summary()


class TestCodeReviewIntegration:
    CODE = {"routes.py": 'from models import *\n    print("hit")\n    assert x is not None'}

    @patch("agents.base.client")
    def test_review_injects_smell_summary(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Review report")
        agent = CodeReviewAgent(project_id=None)
        result = agent.review(self.CODE, pr_description="Add user route")
        content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "smell" in content.lower() or "print" in content.lower()
        assert result.output == "Review report"

    @patch("agents.base.client")
    def test_review_diff_passes_diff_content(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Diff review")
        agent = CodeReviewAgent(project_id=None)
        agent.review_diff("+    print('added line')\n-    logger.info('removed')")
        content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "diff" in content.lower() or "+" in content


# ════════════════════════════════════════════════════════════════════════════════
# DevOpsAgent
# ════════════════════════════════════════════════════════════════════════════════

class TestInfraGapScanner:
    def setup_method(self):
        self.agent = DevOpsAgent.__new__(DevOpsAgent)
        self.agent.project_id = self.agent.memory = None
        self.agent._messages = []

    def test_detects_dockerfile_latest_tag(self):
        files = {"Dockerfile": "FROM python:latest\nCOPY . ."}
        gaps = self.agent._scan_infra_gaps(files)
        assert any("latest" in g.pattern_name.lower() for g in gaps)

    def test_detects_dockerfile_add_instead_of_copy(self):
        files = {"Dockerfile": "FROM python:3.11-slim\nADD requirements.txt ."}
        gaps = self.agent._scan_infra_gaps(files)
        assert any("ADD" in g.pattern_name or "COPY" in g.pattern_name for g in gaps)

    def test_detects_github_actions_mutable_ref(self):
        files = {".github/workflows/ci.yml": "      uses: actions/checkout@main"}
        gaps = self.agent._scan_infra_gaps(files)
        assert any("mutable" in g.pattern_name.lower() or "ref" in g.pattern_name.lower() for g in gaps)

    def test_detects_secret_in_run_step(self):
        files = {".github/workflows/deploy.yml": "      run: deploy --key ${{ secrets.API_KEY }}"}
        gaps = self.agent._scan_infra_gaps(files)
        assert any("secret" in g.pattern_name.lower() for g in gaps)


class TestInfraAntiPatternScanner:
    def setup_method(self):
        self.agent = DevOpsAgent.__new__(DevOpsAgent)
        self.agent.project_id = self.agent.memory = None
        self.agent._messages = []

    def test_detects_open_ssh_to_all(self):
        files = {"main.tf": "from_port = 22\ncidr_blocks = [\"0.0.0.0/0\"]"}
        aps = self.agent._scan_infra_antipatterns(files)
        assert any("ssh" in a.pattern_name.lower() or "22" in a.pattern_name for a in aps)

    def test_detects_unencrypted_rds(self):
        files = {"rds.tf": "  storage_encrypted = false"}
        aps = self.agent._scan_infra_antipatterns(files)
        assert any("encrypt" in a.pattern_name.lower() for a in aps)

    def test_clean_dockerfile_has_no_antipatterns(self):
        files = {"Dockerfile": "FROM python:3.11.9-slim\nCOPY requirements.txt .\nUSER appuser"}
        # latest tag not present — should not trigger that gap
        gaps = self.agent._scan_infra_gaps(files)
        latest_gaps = [g for g in gaps if "latest" in g.pattern_name.lower()]
        assert len(latest_gaps) == 0


class TestInfraIssueDataclass:
    def test_to_summary_has_severity_and_location(self):
        issue = InfraIssue("FROM :latest", "high", "reproducibility", "Dockerfile:1", "FROM python:latest", "pin version", "reproducible builds")
        assert "HIGH" in issue.to_summary()
        assert "Dockerfile:1" in issue.to_summary()


class TestDevOpsIntegration:
    @patch("agents.base.client")
    def test_generate_pipeline_calls_claude(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Pipeline YAML")
        agent = DevOpsAgent(project_id=None)
        result = agent.generate_pipeline("FastAPI + React app", stack="python-fastapi")
        assert result.output == "Pipeline YAML"
        assert mock_client.messages.create.called

    @patch("agents.base.client")
    def test_audit_infra_injects_gap_summary(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("Audit report")
        agent = DevOpsAgent(project_id=None)
        result = agent.audit_infra({
            "Dockerfile": "FROM python:latest\nADD . .",
            ".github/workflows/ci.yml": "uses: actions/checkout@main",
        })
        content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "gap" in content.lower() or "anti-pattern" in content.lower()
        assert result.output == "Audit report"

    @patch("agents.base.client")
    def test_cost_tracking(self, mock_client):
        mock_client.messages.create.return_value = _mock_response("output", input_tokens=3000, output_tokens=1500)
        agent = DevOpsAgent(project_id=None)
        result = agent.generate_pipeline("app")
        assert result.cost_usd > 0
        assert result.input_tokens == 3000


# ════════════════════════════════════════════════════════════════════════════════
# UIUXAgent, MobileAgent, MonetisationAgent — scanner-only tests (no API mock needed)
# ════════════════════════════════════════════════════════════════════════════════

class TestUIUXSignalScanner:
    def setup_method(self):
        self.agent = _make_agent("ui_ux")

    def test_detects_auth_flow(self):
        signals = self.agent._detect_design_signals("User login and signup flow with JWT")
        assert any("auth" in s.signal_type for s in signals)

    def test_detects_billing_signal(self):
        signals = self.agent._detect_design_signals("Stripe billing and subscription plans")
        assert any("billing" in s.signal_type for s in signals)

    def test_detects_mobile(self):
        signals = self.agent._detect_design_signals("Mobile app for iOS and Android")
        assert any("mobile" in s.signal_type for s in signals)

    def test_detects_onboarding(self):
        signals = self.agent._detect_design_signals("User onboarding wizard with 3 steps")
        assert any("onboard" in s.signal_type for s in signals)

    def test_detects_search(self):
        signals = self.agent._detect_design_signals("Search, filter, and sort products")
        assert any("search" in s.signal_type for s in signals)

    def test_simple_feature_no_signals(self):
        signals = self.agent._detect_design_signals("Change the colour of the header")
        assert len(signals) == 0


class TestMobileSignalScanner:
    def setup_method(self):
        self.agent = _make_agent("mobile")

    def test_detects_push_notifications(self):
        signals = self.agent._detect_mobile_signals("Push notification when order ships")
        assert any("push" in s.signal_type or "notif" in s.signal_type for s in signals)

    def test_detects_camera(self):
        signals = self.agent._detect_mobile_signals("Take a photo and upload it")
        assert any("camera" in s.signal_type for s in signals)

    def test_detects_biometrics(self):
        signals = self.agent._detect_mobile_signals("Face ID and Touch ID login")
        assert any("biometric" in s.signal_type for s in signals)

    def test_detects_iap(self):
        signals = self.agent._detect_mobile_signals("In-app purchase paywall for premium")
        assert any("iap" in s.signal_type for s in signals)

    def test_detects_deep_links(self):
        signals = self.agent._detect_mobile_signals("Deep link from email to specific screen")
        assert any("deep" in s.signal_type or "link" in s.signal_type for s in signals)

    def test_no_signals_for_simple_feature(self):
        signals = self.agent._detect_mobile_signals("Display the user profile page")
        assert len(signals) == 0


class TestMonetisationSignalScanner:
    def setup_method(self):
        self.agent = _make_agent("monetisation")

    def test_detects_trial(self):
        signals = self.agent._detect_billing_signals("Free trial for 14 days then paid plan")
        assert any("trial" in s.signal_type for s in signals)

    def test_detects_team_billing(self):
        signals = self.agent._detect_billing_signals("Team seats and per-seat billing")
        assert any("team" in s.signal_type for s in signals)

    def test_detects_annual_plan(self):
        signals = self.agent._detect_billing_signals("Annual subscription with 20% discount")
        assert any("annual" in s.signal_type for s in signals)

    def test_detects_enterprise(self):
        signals = self.agent._detect_billing_signals("Enterprise pricing and custom contracts")
        assert any("enterprise" in s.signal_type for s in signals)

    def test_detects_refunds(self):
        signals = self.agent._detect_billing_signals("Handle refunds and chargebacks from Stripe")
        assert any("dispute" in s.signal_type or "refund" in s.signal_type for s in signals)

    def test_no_signals_simple_billing(self):
        signals = self.agent._detect_billing_signals("Show the current plan name in the header")
        assert len(signals) == 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(text: str, input_tokens: int = 1000, output_tokens: int = 500):
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = [MagicMock(text=text, type="text")]
    r.usage.input_tokens = input_tokens
    r.usage.output_tokens = output_tokens
    return r


def _make_agent(name: str):
    """Create agent instance without memory/project for scanner-only tests."""
    mapping = {
        "backend": "agents.backend_agent.BackendAgent",
        "code_review": "agents.code_review_agent.CodeReviewAgent",
        "devops": "agents.devops_agent.DevOpsAgent",
        "ui_ux": "agents.ui_ux_agent.UIUXAgent",
        "mobile": "agents.mobile_agent.MobileAgent",
        "monetisation": "agents.monetisation_agent.MonetisationAgent",
    }
    import importlib
    mod_path, cls_name = mapping[name].rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    a = cls.__new__(cls)
    a.project_id = a.memory = None
    a._messages = []
    return a
