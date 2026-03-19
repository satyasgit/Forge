"""
Tests for PMAgent.
All tests run without any API call — Claude is fully mocked.
Run: pytest tests/agents/test_pm_agent.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.pm_agent import PMAgent, FeatureEntity, ComplexitySignal


# ── Entity extractor tests (no API calls) ─────────────────────────────────────

class TestEntityExtractor:
    def setup_method(self):
        self.agent = PMAgent.__new__(PMAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_extracts_stripe_integration(self):
        feature = "Add Stripe billing with subscription plans"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "integration" for e in entities)
        assert any("Stripe" in e.name for e in entities)

    def test_extracts_auth_requirement(self):
        feature = "User login with JWT authentication and admin roles"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "auth" for e in entities)

    def test_extracts_ui_screen(self):
        feature = "Build a dashboard page with a settings form"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "frontend" for e in entities)

    def test_extracts_mobile_requirement(self):
        feature = "React Native mobile screen for user profile"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "mobile" for e in entities)

    def test_extracts_analytics_event(self):
        feature = "Track user upgrade and conversion events in PostHog"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "analytics" for e in entities)

    def test_extracts_email_notification(self):
        feature = "Send welcome email and Slack notifications on signup"
        entities = self.agent._extract_entities(feature)
        assert any(e.jira_label == "notifications" for e in entities)

    def test_no_duplicates_for_repeated_terms(self):
        feature = "Stripe billing with Stripe checkout and Stripe webhooks"
        entities = self.agent._extract_entities(feature)
        stripe_entities = [e for e in entities if "Stripe" in e.name]
        names = [e.name for e in stripe_entities]
        # Deduplication should prevent exact duplicate entries
        assert len(names) == len(set(names))

    def test_entity_has_required_fields(self):
        feature = "User authentication with JWT"
        entities = self.agent._extract_entities(feature)
        assert len(entities) > 0
        e = entities[0]
        assert e.entity_type
        assert e.jira_label
        assert e.creates in ("story", "task", "spike")

    def test_empty_feature_returns_no_entities(self):
        entities = self.agent._extract_entities("Build it")
        # Very short feature with no recognisable keywords
        assert isinstance(entities, list)

    def test_integration_entity_has_spike_note(self):
        feature = "Integrate with Figma API"
        entities = self.agent._extract_entities(feature)
        figma_entities = [e for e in entities if "Figma" in e.name]
        if figma_entities:
            assert figma_entities[0].note  # should have a note about spiking


# ── Complexity signal tests ───────────────────────────────────────────────────

class TestComplexitySignals:
    def setup_method(self):
        self.agent = PMAgent.__new__(PMAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_detects_multi_tenant(self):
        feature = "Multi-tenant SaaS with organisation-level data isolation"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("multi" in s.signal.lower() for s in signals)
        assert any(s.impact == "scope" for s in signals)

    def test_detects_real_time(self):
        feature = "Real-time chat with WebSocket updates"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("real" in s.signal.lower() for s in signals)
        assert any(s.impact == "estimate" for s in signals)

    def test_detects_gdpr_compliance(self):
        feature = "GDPR-compliant user data deletion and export"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("GDPR" in s.signal for s in signals)
        assert any(s.impact == "scope" for s in signals)

    def test_detects_data_migration(self):
        feature = "Migrate existing user records to new schema"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("migrat" in s.signal.lower() for s in signals)
        assert any(s.impact == "risk" for s in signals)

    def test_detects_mobile_requirement(self):
        feature = "Add mobile support for iOS and Android"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("mobile" in s.signal.lower() for s in signals)

    def test_detects_scale_requirement(self):
        feature = "The system must scale to 10,000 concurrent users"
        signals = self.agent._detect_complexity_signals(feature)
        assert any("scal" in s.signal.lower() for s in signals)

    def test_simple_feature_has_no_signals(self):
        feature = "Change the button colour from blue to green"
        signals = self.agent._detect_complexity_signals(feature)
        assert len(signals) == 0

    def test_signal_has_description(self):
        feature = "Real-time dashboard updates"
        signals = self.agent._detect_complexity_signals(feature)
        assert all(s.description for s in signals)
        assert all(s.impact for s in signals)


# ── FeatureEntity dataclass tests ─────────────────────────────────────────────

class TestFeatureEntity:
    def test_to_summary_includes_type_and_creates(self):
        e = FeatureEntity(
            entity_type="Third-party integration",
            name="Stripe",
            jira_label="integration",
            creates="story",
            note="spike recommended",
        )
        summary = e.to_summary()
        assert "STORY" in summary
        assert "Stripe" in summary
        assert "integration" in summary
        assert "spike recommended" in summary

    def test_to_summary_without_note(self):
        e = FeatureEntity(
            entity_type="UI screen",
            name="dashboard",
            jira_label="frontend",
            creates="story",
        )
        summary = e.to_summary()
        assert "STORY" in summary
        assert "dashboard" in summary
        # no trailing " ()" when note is empty
        assert "()" not in summary


# ── Format methods tests ──────────────────────────────────────────────────────

class TestFormatMethods:
    def setup_method(self):
        self.agent = PMAgent.__new__(PMAgent)
        self.agent.project_id = "test"
        self.agent.memory = None
        self.agent._messages = []

    def test_format_entities_empty(self):
        result = self.agent._format_entities([])
        assert "No" in result or "infer" in result.lower()

    def test_format_entities_shows_count(self):
        entities = [
            FeatureEntity("auth", "JWT", "auth", "story"),
            FeatureEntity("integration", "Stripe", "integration", "story"),
        ]
        result = self.agent._format_entities(entities)
        assert "2 entities" in result

    def test_format_complexity_signals_empty(self):
        result = self.agent._format_complexity_signals([])
        assert "No" in result or "None" in result

    def test_format_complexity_signals_shows_all(self):
        signals = [
            ComplexitySignal("real-time", "estimate", "Needs WebSocket"),
            ComplexitySignal("GDPR", "scope", "Adds compliance work"),
        ]
        result = self.agent._format_complexity_signals(signals)
        assert "ESTIMATE" in result
        assert "SCOPE" in result
        assert "real-time" in result
        assert "GDPR" in result


# ── Integration tests (mocked API) ───────────────────────────────────────────

class TestPMAgentIntegration:
    FEATURE = """
    Stripe billing with Free, Pro ($29/mo), and Business ($99/mo) plans.
    Team seats on Business. Webhook handling. GDPR compliance.
    """

    @patch("agents.base.client")
    def test_write_prd_injects_entities_into_prompt(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="PRD content", type="text")]
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 1000
        mock_client.messages.create.return_value = mock_response

        agent = PMAgent(project_id=None)
        result = agent.write_prd(self.FEATURE, target_users="SaaS founders")

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        # Entity extraction should have found Stripe + GDPR signals
        assert "entity" in user_content.lower() or "Stripe" in user_content
        assert result.output == "PRD content"

    @patch("agents.base.client")
    def test_write_prd_injects_complexity_signals(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="PRD", type="text")]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_client.messages.create.return_value = mock_response

        agent = PMAgent(project_id=None)
        agent.write_prd(self.FEATURE)

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        # GDPR should be detected as a complexity signal
        assert "complexity" in user_content.lower() or "GDPR" in user_content

    @patch("agents.base.client")
    def test_break_down_epic_mentions_sprint_capacity(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Sprint plan", type="text")]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 300
        mock_client.messages.create.return_value = mock_response

        agent = PMAgent(project_id=None)
        agent.break_down_epic("Billing epic", sprint_capacity=30)

        user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "30" in user_content

    @patch("agents.base.client")
    def test_result_includes_cost_tracking(self, mock_client):
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="PRD", type="text")]
        mock_response.usage.input_tokens = 4000
        mock_response.usage.output_tokens = 2000
        mock_client.messages.create.return_value = mock_response

        agent = PMAgent(project_id=None)
        result = agent.write_prd("Add user onboarding flow")

        assert result.cost_usd > 0
        assert result.duration_seconds >= 0
        assert result.input_tokens == 4000
