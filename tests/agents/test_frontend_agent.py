"""
Tests for FrontendAgent.
All tests run without any API call — Claude is fully mocked.
Run: pytest tests/agents/test_frontend_agent.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.frontend_agent import FrontendAgent, ComponentGap, A11yIssue


# ── Component gap scanner tests (no API calls) ────────────────────────────────

class TestComponentGapScanner:
    def setup_method(self):
        self.agent = FrontendAgent.__new__(FrontendAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_onclick_handler(self):
        code = {"Button.tsx": "<button onClick={handleSave}>Save</button>"}
        gaps = self.agent._scan_components(code)
        assert any("interactive" in g.category.lower() for g in gaps)

    def test_detects_loading_state(self):
        code = {"List.tsx": "{isLoading && <Spinner />}"}
        gaps = self.agent._scan_components(code)
        assert any("loading" in g.pattern_name.lower() for g in gaps)

    def test_detects_error_state(self):
        code = {"Profile.tsx": "{isError && <ErrorBanner message={error.message} />}"}
        gaps = self.agent._scan_components(code)
        assert any("error" in g.pattern_name.lower() for g in gaps)

    def test_detects_zod_form(self):
        code = {"LoginForm.tsx": "const form = useForm({ resolver: zodResolver(schema) })"}
        gaps = self.agent._scan_components(code)
        assert any("form" in g.pattern_name.lower() or "validation" in g.category.lower() for g in gaps)

    def test_detects_useEffect(self):
        code = {"UserData.tsx": "useEffect(() => {\n  fetchUser();\n}, [userId]);"}
        gaps = self.agent._scan_components(code)
        assert any("effect" in g.pattern_name.lower() for g in gaps)

    def test_detects_conditional_render(self):
        code = {"Paywall.tsx": "{isPro ? <Dashboard /> : <UpgradeBanner />}"}
        gaps = self.agent._scan_components(code)
        assert any("conditional" in g.pattern_name.lower() for g in gaps)

    def test_detects_router_navigation(self):
        code = {"Sidebar.tsx": "const navigate = useNavigate();"}
        gaps = self.agent._scan_components(code)
        assert any("navigation" in g.pattern_name.lower() for g in gaps)

    def test_detects_onsubmit_handler(self):
        code = {"Form.tsx": "<form onSubmit={handleSubmit(onSubmit)}>"}
        gaps = self.agent._scan_components(code)
        assert any("interactive" in g.category.lower() for g in gaps)

    def test_skips_test_files(self):
        code = {
            "Button.test.tsx": "onClick={vi.fn()}",
            "Button.stories.tsx": "isLoading={true}",
        }
        gaps = self.agent._scan_components(code)
        assert len(gaps) == 0

    def test_gap_has_required_fields(self):
        code = {"List.tsx": "{loading && <Skeleton />}"}
        gaps = self.agent._scan_components(code)
        if gaps:
            g = gaps[0]
            assert g.severity in ("high", "medium", "low")
            assert "List.tsx:" in g.location
            assert g.example
            assert g.test_template

    def test_location_includes_line_number(self):
        code = {"Card.tsx": "const x = 1;\n{isError && <Alert />}"}
        gaps = self.agent._scan_components(code)
        error_gaps = [g for g in gaps if "error" in g.pattern_name.lower()]
        assert any(":2" in g.location for g in error_gaps)


# ── A11y scanner tests ────────────────────────────────────────────────────────

class TestA11yScanner:
    def setup_method(self):
        self.agent = FrontendAgent.__new__(FrontendAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_img_without_alt(self):
        code = {"Avatar.tsx": '<img src={user.avatar} className="rounded-full" />'}
        issues = self.agent._scan_a11y(code)
        assert any("alt" in issue.pattern_name.lower() for issue in issues)
        assert any(issue.severity == "high" for issue in issues)

    def test_detects_input_without_label(self):
        code = {"Form.tsx": '<input type="email" placeholder="Email" />'}
        issues = self.agent._scan_a11y(code)
        assert any("label" in issue.pattern_name.lower() for issue in issues)

    def test_detects_onclick_on_div(self):
        code = {"Card.tsx": '<div className="card" onClick={handleClick}>'}
        issues = self.agent._scan_a11y(code)
        assert any("non-interactive" in issue.pattern_name.lower() for issue in issues)

    def test_detects_onclick_on_span(self):
        code = {"Nav.tsx": '<span onClick={toggle} className="menu-item">'}
        issues = self.agent._scan_a11y(code)
        assert any("non-interactive" in issue.pattern_name.lower() for issue in issues)

    def test_allows_img_with_alt(self):
        code = {"Avatar.tsx": '<img src={url} alt="User profile photo" />'}
        issues = self.agent._scan_a11y(code)
        alt_issues = [i for i in issues if "alt" in i.pattern_name.lower()]
        assert len(alt_issues) == 0

    def test_allows_decorative_img_with_empty_alt(self):
        code = {"Decoration.tsx": '<img src="/bg.png" alt="" role="presentation" />'}
        issues = self.agent._scan_a11y(code)
        alt_issues = [i for i in issues if "alt" in i.pattern_name.lower()]
        assert len(alt_issues) == 0

    def test_a11y_issue_has_wcag_reference(self):
        code = {"Form.tsx": "<input type='text' />"}
        issues = self.agent._scan_a11y(code)
        if issues:
            assert all(i.wcag for i in issues)

    def test_a11y_issue_has_fix_and_test(self):
        code = {"Card.tsx": '<img src={url} className="photo" />'}
        issues = self.agent._scan_a11y(code)
        if issues:
            assert all(i.fix for i in issues)
            assert all(i.test for i in issues)

    def test_skips_comments(self):
        code = {"Component.tsx": "// <img src={url} /> old img without alt"}
        issues = self.agent._scan_a11y(code)
        assert len(issues) == 0

    def test_clean_component_has_no_a11y_issues(self):
        code = {"Button.tsx": '''
export function IconButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button aria-label={label} onClick={onClick} className="p-2">
      <XIcon width={16} height={16} />
    </button>
  );
}
'''}
        issues = self.agent._scan_a11y(code)
        # No missing-label or non-interactive-element issues
        critical = [i for i in issues if i.severity == "high"]
        assert len(critical) == 0


# ── ComponentGap + A11yIssue dataclass tests ──────────────────────────────────

class TestDataclasses:
    def test_component_gap_to_summary(self):
        gap = ComponentGap(
            pattern_name="Loading state without test",
            severity="medium",
            category="states",
            location="List.tsx:14",
            evidence="{isLoading && <Skeleton />}",
            test_template="it('shows loading...')",
            example="...",
        )
        summary = gap.to_summary()
        assert "MEDIUM" in summary
        assert "List.tsx:14" in summary
        assert "states" in summary

    def test_a11y_issue_to_summary(self):
        issue = A11yIssue(
            pattern_name="Image without alt text",
            severity="high",
            wcag="1.1.1",
            location="Avatar.tsx:3",
            evidence='<img src={url} />',
            fix='<img src={url} alt="Profile photo" />',
            test='screen.getByAltText(/profile/i)',
        )
        summary = issue.to_summary()
        assert "HIGH" in summary
        assert "1.1.1" in summary
        assert "Avatar.tsx:3" in summary


# ── Format methods tests ──────────────────────────────────────────────────────

class TestFormatMethods:
    def setup_method(self):
        self.agent = FrontendAgent.__new__(FrontendAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_format_gap_summary_empty(self):
        result = self.agent._format_gap_summary([])
        assert "No" in result

    def test_format_gap_summary_orders_by_severity(self):
        gaps = [
            ComponentGap("Low", "low", "c", "f:1", "e", "t", "ex"),
            ComponentGap("High", "high", "c", "f:2", "e", "t", "ex"),
            ComponentGap("Med", "medium", "c", "f:3", "e", "t", "ex"),
        ]
        result = self.agent._format_gap_summary(gaps)
        assert result.index("HIGH") < result.index("MEDIUM")
        assert result.index("MEDIUM") < result.index("LOW")

    def test_format_a11y_summary_empty(self):
        result = self.agent._format_a11y_summary([])
        assert "No" in result

    def test_format_a11y_summary_shows_count(self):
        issues = [
            A11yIssue("Missing alt", "high", "1.1.1", "f:1", "e", "fix", "test"),
            A11yIssue("Missing label", "high", "1.3.1", "f:2", "e", "fix", "test"),
        ]
        result = self.agent._format_a11y_summary(issues)
        assert "2 accessibility" in result


# ── Integration tests (mocked API) ───────────────────────────────────────────

class TestFrontendAgentIntegration:
    COMPONENT_CODE = {
        "UserProfile.tsx": '''
export function UserProfile({ userId }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const handleSave = () => {};

  if (loading) return <div>Loading...</div>;
  if (error) return <div>{error}</div>;

  return (
    <div>
      <img src="/avatar.jpg" />
      <input placeholder="Name" />
      <div onClick={handleSave}>Save</div>
    </div>
  );
}
''',
    }

    @patch("agents.base.client")
    def test_build_components_injects_gap_summary(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Components here", type="text")]
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 1000
        mock_client.messages.create.return_value = mock_response

        agent = FrontendAgent(project_id=None)
        result = agent.build_components(
            design_spec="User profile with edit form",
            existing_components=self.COMPONENT_CODE,
        )

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "gap" in user_content.lower()
        assert result.output == "Components here"

    @patch("agents.base.client")
    def test_build_components_injects_a11y_summary(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Fixed components", type="text")]
        mock_response.usage.input_tokens = 1500
        mock_response.usage.output_tokens = 700
        mock_client.messages.create.return_value = mock_response

        agent = FrontendAgent(project_id=None)
        agent.build_components(
            design_spec="Profile component",
            existing_components=self.COMPONENT_CODE,
        )

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "accessibility" in user_content.lower() or "a11y" in user_content.lower()

    @patch("agents.base.client")
    def test_write_tests_passes_component_to_claude(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Test file", type="text")]
        mock_response.usage.input_tokens = 800
        mock_response.usage.output_tokens = 400
        mock_client.messages.create.return_value = mock_response

        agent = FrontendAgent(project_id=None)
        agent.write_tests_for_component(
            "UserProfile",
            self.COMPONENT_CODE["UserProfile.tsx"],
            api_routes={"PATCH /api/users/:id": "update user"},
        )

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "UserProfile" in user_content

    @patch("agents.base.client")
    def test_audit_components_scans_and_sends_to_claude(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Audit report", type="text")]
        mock_response.usage.input_tokens = 600
        mock_response.usage.output_tokens = 300
        mock_client.messages.create.return_value = mock_response

        agent = FrontendAgent(project_id=None)
        result = agent.audit_components(self.COMPONENT_CODE)

        assert result.output == "Audit report"
        # Pre-scan results should be in the prompt
        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "UserProfile.tsx" in user_content

    @patch("agents.base.client")
    def test_cost_tracking_works(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Output", type="text")]
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 2500
        mock_client.messages.create.return_value = mock_response

        agent = FrontendAgent(project_id=None)
        result = agent.build_components(design_spec="Test component")

        assert result.cost_usd > 0
        assert result.input_tokens == 5000
        assert result.output_tokens == 2500
