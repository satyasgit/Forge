"""
UI/UX Skill: design pattern and heuristic library.
Mirrors skills/security/owasp.py — structured reference data
injected into UIUXAgent's system prompt so it produces consistent,
complete design specs that engineers can implement without questions.
"""

# ── Nielsen's 10 Usability Heuristics ────────────────────────────────────────
# Injected as evaluation criteria into every design review.

USABILITY_HEURISTICS: dict[str, dict] = {
    "H01": {
        "name": "Visibility of system status",
        "description": "Always keep users informed through appropriate feedback.",
        "examples": ["Loading spinners", "Progress bars", "Toast notifications", "Step indicators"],
        "check": "Does the user always know what's happening?",
        "anti_patterns": ["Silent failures", "Operations with no feedback", "Missing loading states"],
    },
    "H02": {
        "name": "Match between system and real world",
        "description": "Use words, phrases, and concepts familiar to the user.",
        "examples": ["'Save' not 'Persist'", "Shopping cart not 'transaction queue'"],
        "check": "Would a non-technical user understand every label?",
        "anti_patterns": ["Technical jargon in UI copy", "ID numbers shown to users", "Error codes"],
    },
    "H03": {
        "name": "User control and freedom",
        "description": "Support undo and redo. Provide emergency exits.",
        "examples": ["Undo delete", "Cancel button on every form", "Back navigation"],
        "check": "Can the user easily undo every action?",
        "anti_patterns": ["Irreversible actions without confirmation", "No cancel on modals", "Dead ends"],
    },
    "H04": {
        "name": "Consistency and standards",
        "description": "Same words, situations, and actions should mean the same thing.",
        "examples": ["Primary button always blue", "Destructive always red", "Icons consistent"],
        "check": "Are patterns consistent across every screen?",
        "anti_patterns": ["Save in different positions per screen", "Different terminology for same concept"],
    },
    "H05": {
        "name": "Error prevention",
        "description": "Design carefully to prevent problems from occurring.",
        "examples": ["Disable submit until form valid", "Confirm destructive actions", "Input masks"],
        "check": "Can the user make a mistake that's hard to recover from?",
        "anti_patterns": ["Delete without confirmation", "No input constraints on fields"],
    },
    "H06": {
        "name": "Recognition rather than recall",
        "description": "Minimize user's memory load. Make options visible.",
        "examples": ["Autocomplete", "Recent searches", "Visible navigation", "Contextual tooltips"],
        "check": "Does the user need to remember anything from a previous screen?",
        "anti_patterns": ["Hidden commands", "Requiring users to remember exact syntax"],
    },
    "H07": {
        "name": "Flexibility and efficiency of use",
        "description": "Allow experts to shortcut common tasks.",
        "examples": ["Keyboard shortcuts", "Bulk actions", "Quick filters", "Saved views"],
        "check": "Can a power user do this 10x faster than a new user?",
        "anti_patterns": ["Forced step-by-step wizards for experts", "No bulk operations"],
    },
    "H08": {
        "name": "Aesthetic and minimalist design",
        "description": "Interfaces should not contain irrelevant information.",
        "examples": ["Progressive disclosure", "Hide advanced options by default"],
        "check": "Is every element on this screen earning its place?",
        "anti_patterns": ["Too many options at once", "Competing CTAs", "Dense information"],
    },
    "H09": {
        "name": "Help users recognise and recover from errors",
        "description": "Error messages should be expressed in plain language.",
        "examples": ['"Email is already registered" not "UNIQUE constraint failed"'],
        "check": "Can the user understand what went wrong and how to fix it?",
        "anti_patterns": ["Stack traces to users", "Error codes", "Generic 'Something went wrong'"],
    },
    "H10": {
        "name": "Help and documentation",
        "description": "Provide easy-to-search documentation and contextual help.",
        "examples": ["Tooltip on hover", "? icon linking to docs", "In-context guidance"],
        "check": "Can a confused user find help without leaving the page?",
        "anti_patterns": ["No contextual help", "Docs only accessible from footer"],
    },
}

# ── Component spec patterns ───────────────────────────────────────────────────
# Each component type has a standard set of states UIUXAgent must specify.

COMPONENT_SPEC_REQUIREMENTS: dict[str, dict] = {
    "button": {
        "required_states": ["default", "hover", "active/pressed", "disabled", "loading"],
        "required_variants": ["primary", "secondary", "destructive", "ghost/text"],
        "required_props": ["label", "onClick", "disabled", "isLoading", "size", "variant"],
        "accessibility": ["role=button", "aria-disabled when disabled", "aria-busy when loading"],
    },
    "form_input": {
        "required_states": ["empty", "focused", "filled", "error", "disabled", "readonly"],
        "required_variants": ["text", "email", "password", "number", "textarea"],
        "required_props": ["label", "placeholder", "value", "error", "helperText", "required"],
        "accessibility": ["htmlFor/id pair", "aria-describedby for errors", "aria-required"],
    },
    "modal_dialog": {
        "required_states": ["open", "closed", "loading (content)", "error (content)"],
        "required_variants": ["confirmation", "form", "informational", "full-screen mobile"],
        "required_props": ["isOpen", "onClose", "title", "children", "footer"],
        "accessibility": ["role=dialog", "aria-labelledby", "focus trap", "Escape to close"],
    },
    "data_table": {
        "required_states": ["loading", "empty", "populated", "error", "selected rows"],
        "required_variants": ["basic", "sortable", "selectable", "paginated"],
        "required_props": ["columns", "data", "isLoading", "onRowClick", "pagination"],
        "accessibility": ["role=table", "aria-sort on headers", "caption", "keyboard navigation"],
    },
    "toast_notification": {
        "required_states": ["appearing", "visible", "dismissing"],
        "required_variants": ["success", "error", "warning", "info"],
        "required_props": ["message", "variant", "duration", "onDismiss", "action"],
        "accessibility": ["role=alert for errors", "role=status for success", "auto-dismiss"],
    },
    "empty_state": {
        "required_states": ["first-time user (no data yet)", "filtered result (no match)", "error"],
        "required_variants": ["with CTA", "informational only"],
        "required_props": ["illustration", "title", "description", "action (optional)"],
        "accessibility": ["Descriptive heading", "Action button with clear label"],
    },
}

# ── Screen spec template ──────────────────────────────────────────────────────
# Injected into UIUXAgent prompts as the output format.

SCREEN_SPEC_TEMPLATE = """
## Screen: {screen_name}

**Purpose:** {one_sentence_purpose}
**User goal:** {what_user_wants_to_accomplish}
**Entry points:** {how_user_arrives_here}

### Layout
{describe_layout: sidebar/topnav/full-width/card-based/etc}

### Components
| Component | Variant | Data source | States needed |
|-----------|---------|-------------|---------------|
| {name}    | {variant} | {api_endpoint} | {loading, error, empty, populated} |

### User flow
1. User arrives → {initial_state}
2. User does {action} → {system_response}
3. Success → {outcome}
4. Error → {error_handling}

### Mobile adaptation
{describe_how_this_screen_changes_on_mobile}

### Edge cases
- Empty state: {what_shows_when_no_data}
- Error state: {what_shows_on_API_error}
- Loading: {skeleton_or_spinner}
- Permissions: {what_if_user_lacks_access}

### Copy
- Page title: "{exact_title_text}"
- Primary CTA: "{exact_button_label}"
- Empty state heading: "{exact_empty_heading}"
- Error message: "{plain_language_error}"
"""

# ── Design token definitions ──────────────────────────────────────────────────

DESIGN_TOKEN_SPEC = {
    "colors": {
        "primary": "Brand colour — use for primary CTAs, links, active states",
        "primary_hover": "10% darker than primary",
        "destructive": "Red — use for delete, errors, critical warnings",
        "success": "Green — use for completed, paid, active",
        "warning": "Amber — use for trials expiring, low quota, degraded",
        "neutral_50": "Page background",
        "neutral_100": "Card background",
        "neutral_900": "Primary text",
        "neutral_600": "Secondary text",
        "neutral_400": "Placeholder / disabled text",
    },
    "typography": {
        "display": "32px/40px bold — page hero headings",
        "h1": "24px/32px semibold — page titles",
        "h2": "20px/28px semibold — section headings",
        "h3": "16px/24px semibold — card titles, subsections",
        "body": "16px/24px regular — body copy",
        "small": "14px/20px regular — helper text, labels",
        "xs": "12px/16px regular — captions, timestamps",
        "mono": "13px/20px mono — code, IDs, tokens",
    },
    "spacing": {
        "4": "4px — tight gaps between related elements",
        "8": "8px — internal padding, icon-to-label gap",
        "12": "12px — form field gap",
        "16": "16px — card padding",
        "24": "24px — section gap",
        "32": "32px — page section gap",
        "48": "48px — major section divider",
    },
    "border_radius": {
        "sm": "4px — inputs, small badges",
        "md": "8px — buttons, cards",
        "lg": "12px — modals, large cards",
        "full": "9999px — pills, avatars",
    },
}
