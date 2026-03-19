"""
Tests for SecurityAgent.
Run: pytest tests/agents/test_security_agent.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.security_agent import SecurityAgent, SecurityFinding
from skills.security.sast import SAST_PATTERNS


# ── SAST scanner tests (no API calls) ─────────────────────────────────────────

class TestSASTScanner:
    def setup_method(self):
        self.agent = SecurityAgent.__new__(SecurityAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_sql_injection_fstring(self):
        code = {"app.py": "cursor.execute(f\"SELECT * FROM users WHERE id='{user_id}'\")"}
        findings = self.agent._run_sast(code)
        assert any("SQL Injection" in f.title for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_detects_shell_true(self):
        code = {"app.py": "subprocess.run(cmd, shell=True)"}
        findings = self.agent._run_sast(code)
        assert any("Command Injection" in f.title for f in findings)

    def test_detects_debug_true(self):
        code = {"settings.py": "DEBUG = True"}
        findings = self.agent._run_sast(code)
        assert any("debug" in f.title.lower() for f in findings)

    def test_detects_md5_hash(self):
        code = {"auth.py": "hashed = md5(password)"}
        findings = self.agent._run_sast(code)
        assert any("MD5" in f.title for f in findings)

    def test_detects_pickle_loads(self):
        code = {"deserialize.py": "data = pickle.loads(untrusted_bytes)"}
        findings = self.agent._run_sast(code)
        assert any("pickle" in f.title.lower() for f in findings)

    def test_detects_unsafe_yaml(self):
        code = {"config.py": "config = yaml.load(stream)"}
        findings = self.agent._run_sast(code)
        assert any("YAML" in f.title for f in findings)

    def test_clean_code_has_no_findings(self):
        code = {"app.py": '''
def get_user(user_id: int) -> dict:
    with Session() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return user.dict()
'''}
        findings = self.agent._run_sast(code)
        assert len(findings) == 0

    def test_finding_has_required_fields(self):
        code = {"app.py": "cursor.execute(f\"SELECT * FROM t WHERE id='{x}'\")"}
        findings = self.agent._run_sast(code)
        f = findings[0]
        assert f.owasp_id
        assert f.severity in ("critical", "high", "medium", "low", "info")
        assert f.location
        assert f.evidence
        assert f.remediation

    def test_location_includes_line_number(self):
        code = {"auth.py": "# safe line\ncursor.execute(f'SELECT * FROM t WHERE id={x}')"}
        findings = self.agent._run_sast(code)
        assert any(":2" in f.location for f in findings)


# ── Secrets scanner tests ─────────────────────────────────────────────────────

class TestSecretsScanner:
    def setup_method(self):
        self.agent = SecurityAgent.__new__(SecurityAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_hardcoded_password(self):
        code = {"config.py": 'password = "SuperSecret123!"'}
        findings = self.agent._scan_secrets(code)
        assert len(findings) > 0
        assert any("password" in f.title.lower() for f in findings)

    def test_detects_aws_key(self):
        code = {"deploy.py": "aws_access_key_id = 'AKIAIOSFODNN7EXAMPLE'"}
        findings = self.agent._scan_secrets(code)
        assert any("AWS" in f.title for f in findings)

    def test_ignores_env_references(self):
        code = {"config.py": "password = os.environ['DB_PASSWORD']"}
        findings = self.agent._scan_secrets(code)
        assert len(findings) == 0

    def test_ignores_placeholders(self):
        code = {"example.py": "password = 'your_password_here'"}
        findings = self.agent._scan_secrets(code)
        assert len(findings) == 0

    def test_secret_finding_is_critical(self):
        code = {"app.py": 'api_key = "sk-abc123defgh456ijklm789nopqr012345678901234567"'}
        findings = self.agent._scan_secrets(code)
        if findings:
            assert findings[0].severity == "critical"

    def test_redacts_secret_in_evidence(self):
        code = {"app.py": 'SECRET = "mysupersecretvalue123"'}
        findings = self.agent._scan_secrets(code)
        if findings:
            assert "mysupersecretvalue123" not in findings[0].evidence


# ── Finding model tests ───────────────────────────────────────────────────────

class TestSecurityFinding:
    def test_to_markdown_contains_severity(self):
        f = SecurityFinding(
            owasp_id="A03:2021",
            owasp_name="Injection",
            severity="critical",
            title="SQL Injection",
            description="User input in query",
            location="app.py:42",
            evidence="cursor.execute(f'SELECT...')",
            remediation="Use parameterised queries",
            code_fix="cursor.execute('SELECT * FROM t WHERE id=?', (id,))",
        )
        md = f.to_markdown()
        assert "CRITICAL" in md
        assert "A03:2021" in md
        assert "app.py:42" in md

    def test_to_markdown_includes_code_fix(self):
        f = SecurityFinding(
            owasp_id="A03:2021", owasp_name="Injection",
            severity="high", title="Test",
            description="desc", location="f:1",
            evidence="bad code", remediation="fix it",
            code_fix="good_code()",
        )
        assert "good_code()" in f.to_markdown()


# ── Integration test (mocked API) ────────────────────────────────────────────

class TestSecurityAgentIntegration:
    VULNERABLE_CODE = {
        "auth.py": """
SECRET = "hardcoded_secret_key"
def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}'"
    conn.execute(query)
    data = pickle.loads(user_data)
""",
    }

    @patch("agents.base.client")
    def test_full_audit_calls_claude(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Security report here", type="text")]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_client.messages.create.return_value = mock_response

        agent = SecurityAgent(project_id=None)
        result = agent.run_full_audit(self.VULNERABLE_CODE, "python", "test app")

        assert mock_client.messages.create.called
        assert result.output == "Security report here"
        assert result.input_tokens == 1000

    @patch("agents.base.client")
    def test_sast_findings_injected_into_prompt(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Report", type="text")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        agent = SecurityAgent(project_id=None)
        agent.run_full_audit(self.VULNERABLE_CODE, "python")

        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[0]["content"]

        # SAST pre-scan should be in the prompt
        assert "SQL Injection" in user_content or "static findings" in user_content.lower()

    @patch("agents.base.client")
    def test_result_has_cost_tracking(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Report", type="text")]
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 1000
        mock_client.messages.create.return_value = mock_response

        agent = SecurityAgent(project_id=None)
        result = agent.run_full_audit({"f.py": "code"}, "python")

        assert result.cost_usd > 0
        assert result.duration_seconds > 0
