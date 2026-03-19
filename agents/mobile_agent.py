"""
Mobile Agent — fully working React Native / Expo builder.
Pre-scans feature requests for navigation, auth, notifications,
IAP, and offline requirements before calling Claude.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.mobile.expo_patterns import EXPO_SCREEN_TEMPLATE, EXPO_AUTH_FLOW, EXPO_ROUTER_STRUCTURE, PUSH_NOTIFICATIONS, APP_STORE_CHECKLIST

@dataclass
class MobileSignal:
    signal_type: str; description: str; what_to_build: str
    def to_summary(self): return f"[{self.signal_type.upper()}] {self.description} → {self.what_to_build}"

class MobileAgent(BaseAgent):
    name = "mobile"
    role = "Senior React Native / Expo Engineer"
    enabled_tools = ["write_file", "run_command"]

    @property
    def system_prompt(self) -> str:
        checklist = "\n".join(f"  - {item}" for item in APP_STORE_CHECKLIST[:6])
        return textwrap.dedent(f"""
            You are a senior React Native engineer using Expo SDK 51+.
            Stack: React Native, Expo, TypeScript, NativeWind, React Query, Expo Router v3.

            ## Screen template (use for every screen):
            {EXPO_SCREEN_TEMPLATE}

            ## Auth flow template:
            {EXPO_AUTH_FLOW}

            ## Expo Router file structure:
            {EXPO_ROUTER_STRUCTURE}

            ## Push notifications setup:
            {PUSH_NOTIFICATIONS}

            ## App Store submission checklist (first 6 items):
            {checklist}

            ## Output for every task:

            ### SCREENS
            Complete .tsx file for each screen using the screen template.

            ### NAVIGATION
            Expo Router file structure showing exact file paths.

            ### API INTEGRATION
            React Query hooks with proper cache keys and optimistic updates.

            ### PLATFORM DIFFERENCES
            Any iOS vs Android differences in behaviour or UI.

            ### PERMISSIONS
            Exact permission strings needed in app.json for each feature.

            ### APP.JSON CHANGES
            Any plugins, permissions, or config needed.

            ## Non-negotiable:
            - TypeScript strict — no any, all props typed
            - NativeWind (className) for all styling
            - useSafeAreaInsets on every screen
            - accessibilityLabel on every Pressable
            - Haptic feedback on primary actions (expo-haptics)
            - SecureStore for tokens (never AsyncStorage for sensitive data)
            - Keyboard avoiding view on forms
            - React Query for all server state
        """).strip()

    def build_screens(self, feature: str, screens: list[str] | None = None, context: str = "") -> AgentResult:
        signals = self._detect_mobile_signals(feature)
        screens_text = ", ".join(screens) if screens else "Infer screens from feature description."
        task = textwrap.dedent(f"""
            Build React Native screens for this feature.

            Feature: {feature}
            Screens needed: {screens_text}
            Context: {context or "Expo Router v3, NativeWind, React Query."}

            Pre-detected mobile signals (build all):
            {self._format_signals(signals)}

            Output each screen as a complete .tsx file + navigation structure.
        """).strip()
        return self.run(task)

    MOBILE_SIGNAL_PATTERNS = [
        (r"\bpush.?notif|notification\b", "push_notifications", "expo-notifications setup + permission request + token registration"),
        (r"\boffline|no.?internet|cache\b", "offline_support", "React Query persistence + offline indicator + queue sync"),
        (r"\biap|in.?app.?purchase|subscribe|paywall\b", "iap", "RevenueCat + Paywall screen + restore purchases flow"),
        (r"\bcamera|photo|image|scan\b", "camera", "expo-camera + expo-image-picker + permission handling"),
        (r"\blocation|map|gps|geoloc\b", "location", "expo-location + permission request + background location if needed"),
        (r"\bbiometric|face.?id|touch.?id|fingerprint\b", "biometrics", "expo-local-authentication + fallback to PIN"),
        (r"\bdeep.?link|universal.?link|url.?scheme\b", "deep_links", "Expo Router deep link config + app.json scheme"),
        (r"\bwidget|live.?activity|home.?screen\b", "widgets", "expo-widgets or react-native-widget-extension setup note"),
        (r"\bshare|social|clipboard\b", "sharing", "expo-sharing + expo-clipboard integration"),
    ]

    def _detect_mobile_signals(self, text: str) -> list[MobileSignal]:
        signals = []
        for regex, signal_type, what_to_build in self.MOBILE_SIGNAL_PATTERNS:
            if re.search(regex, text, re.IGNORECASE):
                match = re.search(regex, text, re.IGNORECASE)
                signals.append(MobileSignal(signal_type, f"Detected: '{match.group(0)}'", what_to_build))
        return signals

    def _format_signals(self, signals: list[MobileSignal]) -> str:
        if not signals: return "No specific mobile signals detected."
        return "\n".join(["Mobile signals:"] + [f"  {s.to_summary()}" for s in signals])
