"""
Code Review Skill: pattern library for the CodeReviewAgent.
Mirrors skills/security/sast.py exactly — each entry is a named
pattern with a regex, severity, category, description, and fix.
The agent runs this locally before calling Claude to pre-tag findings
by severity so the AI focuses on explaining and fixing, not finding.
"""

# ── Code smell patterns ────────────────────────────────────────────────────────

CODE_SMELL_PATTERNS: list[dict] = [
    # ── Naming ──────────────────────────────────────────────────────────────────
    {
        "name": "Single-letter variable name (non-loop)",
        "regex": r"^\s+(?!for\s+)\b([a-z])\s*=\s*(?![\[\(\"'])",
        "severity": "low",
        "category": "naming",
        "description": "Single-letter variable makes code intent opaque.",
        "fix": "Use descriptive names: user_id, subscription, response_data.",
        "exceptions": ["i", "j", "k", "x", "y", "n", "e"],
    },
    {
        "name": "Magic number (unexplained literal)",
        "regex": r"(?<!['\"\w])(?<!\.)\b(?!0|1|2|100|1000)\d{2,}\b(?!['\"])",
        "severity": "low",
        "category": "readability",
        "description": "Unexplained number literal — should be a named constant.",
        "fix": "MAX_RETRIES = 5\nTRIAL_DAYS = 14\nPAGE_SIZE = 50",
        "exceptions": [],
    },
    {
        "name": "Function longer than 40 lines",
        "regex": r"def \w+\([^)]*\).*:",
        "severity": "medium",
        "category": "complexity",
        "description": "Functions over 40 lines usually do too much — extract sub-functions.",
        "fix": "Extract helper functions. Each function should do exactly one thing.",
        "note": "Checked by line count, not regex — regex marks the function start",
    },
    {
        "name": "Deeply nested code (4+ levels)",
        "regex": r"^ {16,}\S",
        "severity": "medium",
        "category": "complexity",
        "description": "4+ levels of indentation — high cognitive load, hard to test.",
        "fix": "Use early returns (guard clauses) to flatten nesting:\nif not condition: return\nif error: raise\n# happy path here",
    },
    {
        "name": "Boolean parameter (flag argument)",
        "regex": r"def \w+\([^)]*,\s*\w+\s*:\s*bool[^)]*\)",
        "severity": "medium",
        "category": "design",
        "description": "Boolean parameter is a code smell — function does two different things.",
        "fix": "Split into two functions: send_email() and send_email_async()\nOr use an Enum: mode=EmailMode.SYNC",
    },

    # ── Error handling ────────────────────────────────────────────────────────
    {
        "name": "Returning None for error (should raise)",
        "regex": r"except\s+\w+.*:\s*\n\s+return None",
        "severity": "high",
        "category": "error_handling",
        "description": "Returning None on exception forces callers to check for None everywhere.",
        "fix": "Raise a specific exception. Let the global handler convert it to HTTP 500/404.",
    },
    {
        "name": "Catching and re-raising base Exception",
        "regex": r"except Exception as \w+:\s*\n\s+raise",
        "severity": "low",
        "category": "error_handling",
        "description": "Catching Exception to re-raise — same as not catching. Remove the try/except.",
        "fix": "Only catch exceptions you can meaningfully handle at this level.",
    },
    {
        "name": "Print statement in production code",
        "regex": r"^\s+print\s*\(",
        "severity": "medium",
        "category": "observability",
        "description": "print() instead of logging — no log levels, no structured output, stdout only.",
        "fix": "import logging\nlogger = logging.getLogger(__name__)\nlogger.info('message', extra={'user_id': uid})",
    },
    {
        "name": "TODO/FIXME/HACK comment",
        "regex": r"#\s*(?:TODO|FIXME|HACK|XXX|BUG)\b",
        "severity": "low",
        "category": "tech_debt",
        "description": "Technical debt comment — should be a Jira ticket, not a comment.",
        "fix": "Create a Jira ticket. Replace comment with: # See PROJ-123",
    },

    # ── Python-specific ────────────────────────────────────────────────────────
    {
        "name": "assert used for runtime validation",
        "regex": r"^\s+assert\s+(?!.*test|.*spec)",
        "severity": "high",
        "category": "correctness",
        "description": "assert is disabled with -O flag — never use for runtime validation.",
        "fix": "if not condition:\n    raise ValueError('Condition must be true')",
    },
    {
        "name": "Comparing to None with ==",
        "regex": r"(?:==|!=)\s*None\b",
        "severity": "low",
        "category": "style",
        "description": "Use 'is None' / 'is not None' — None has only one instance.",
        "fix": "if user is None:\nif result is not None:",
    },
    {
        "name": "String formatting with % operator",
        "regex": r'["\'].*%\s*(?:\w+|\()',
        "severity": "low",
        "category": "style",
        "description": "Old-style % string formatting — use f-strings or .format().",
        "fix": 'f"Hello {name}" or "Hello {}".format(name)',
    },
    {
        "name": "Mutable class attribute",
        "regex": r"class \w+.*:\s*\n(?:\s+\w.*\n)*\s+\w+\s*(?:=\s*\[\s*\]|\s*=\s*\{\s*\})",
        "severity": "high",
        "category": "correctness",
        "description": "Mutable class attribute shared across ALL instances — silent state sharing bug.",
        "fix": "Move to __init__:\ndef __init__(self):\n    self.items = []",
    },
    {
        "name": "Star import",
        "regex": r"from \w+ import \*",
        "severity": "medium",
        "category": "maintainability",
        "description": "Star import pollutes namespace and makes it unclear where names come from.",
        "fix": "from module import SpecificThing, AnotherThing",
    },

    # ── TypeScript / JavaScript ───────────────────────────────────────────────
    {
        "name": "any type annotation",
        "regex": r":\s*any\b|as\s+any\b",
        "severity": "high",
        "category": "type_safety",
        "description": "TypeScript `any` disables type checking — defeats the purpose of TypeScript.",
        "fix": "Use specific types, generics, or `unknown` with type narrowing.",
    },
    {
        "name": "Non-null assertion operator",
        "regex": r"\w+!(?:\.|$|\[)",
        "severity": "medium",
        "category": "correctness",
        "description": "Non-null assertion (!) tells TypeScript to trust you — runtime crash if wrong.",
        "fix": "Add proper null check: if (user) { user.name }\nOr use optional chaining: user?.name",
    },
    {
        "name": "console.log in production code",
        "regex": r"console\.(log|warn|error)\s*\(",
        "severity": "medium",
        "category": "observability",
        "description": "console.log in production — use a structured logger.",
        "fix": "import { logger } from '@/lib/logger'\nlogger.info('message', { userId })",
    },
    {
        "name": "useEffect with missing dependency",
        "regex": r"useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\w+\s*\([^}]*\}\s*,\s*\[\s*\]\s*\)",
        "severity": "medium",
        "category": "correctness",
        "description": "useEffect with empty deps but uses variables — stale closure bug.",
        "fix": "Add all referenced variables to the dependency array.\nOr use useCallback for stable function references.",
    },
]

# ── Architecture smell patterns ───────────────────────────────────────────────
# Higher-level issues that can't be caught by single-line regex alone.
# Used by CodeReviewAgent to prompt Claude to check for these explicitly.

ARCHITECTURE_SMELLS: list[dict] = [
    {
        "name": "God class",
        "signal": "Class with > 10 methods or > 200 lines",
        "description": "Class that knows too much and does too much — violates Single Responsibility.",
        "fix": "Extract cohesive groups of methods into separate classes.",
        "category": "design",
        "severity": "high",
    },
    {
        "name": "Anemic domain model",
        "signal": "Model class with only fields, all logic in service",
        "description": "Domain object that is just a data bag — logic scattered in services.",
        "fix": "Move validation and business rules into the model itself.",
        "category": "design",
        "severity": "medium",
    },
    {
        "name": "Feature envy",
        "signal": "Method that calls many methods on another object",
        "description": "Method is more interested in another class's data than its own.",
        "fix": "Move the method to the class it envies.",
        "category": "design",
        "severity": "medium",
    },
    {
        "name": "Circular import",
        "signal": "Module A imports from B, B imports from A",
        "description": "Circular imports signal tight coupling and confuse the import system.",
        "fix": "Extract shared types to a third module. Use TYPE_CHECKING guard for type-only imports.",
        "category": "architecture",
        "severity": "high",
    },
    {
        "name": "Missing abstraction layer",
        "signal": "Controller/route directly constructs objects from other domains",
        "description": "No abstraction between layers — change in one layer breaks another.",
        "fix": "Introduce a service layer between routes and repositories.",
        "category": "architecture",
        "severity": "high",
    },
    {
        "name": "Primitive obsession",
        "signal": "Many string/int params where a value object should be used",
        "description": "Using primitives for domain concepts (email as str, money as float).",
        "fix": "Create value objects: Email, Money, UserId — validated on construction.",
        "category": "design",
        "severity": "medium",
    },
]

# ── Complexity metrics ────────────────────────────────────────────────────────

COMPLEXITY_THRESHOLDS = {
    "cyclomatic_complexity": {
        "good": "1-5 — simple, straightforward",
        "warning": "6-10 — moderately complex, consider refactoring",
        "critical": "11+ — too complex, must refactor before merging",
        "tool": "radon cc -s -a src/",
    },
    "cognitive_complexity": {
        "good": "0-5",
        "warning": "6-15",
        "critical": "16+",
        "tool": "Sonar or flake8-cognitive-complexity plugin",
    },
    "function_length": {
        "good": "< 20 lines",
        "warning": "20-40 lines",
        "critical": "> 40 lines — must be split",
    },
    "class_length": {
        "good": "< 100 lines",
        "warning": "100-200 lines",
        "critical": "> 200 lines — God class, split immediately",
    },
    "file_length": {
        "good": "< 200 lines",
        "warning": "200-400 lines",
        "critical": "> 400 lines — split into modules",
    },
}

# ── PR review checklist ───────────────────────────────────────────────────────
# Injected into CodeReviewAgent — structured checklist Claude fills in.

PR_REVIEW_CHECKLIST = {
    "correctness": [
        "Logic handles all branches (happy path + every error path)",
        "Edge cases: empty list, None, zero, max int, unicode",
        "No off-by-one errors in loops or pagination",
        "Concurrent access — any shared mutable state?",
        "Data types match across layers (str UUID not mixed with int PK)",
    ],
    "security": [
        "No hardcoded secrets or credentials",
        "All user input validated before use",
        "Auth check on every protected endpoint",
        "No SQL string concatenation",
        "Sensitive data not logged",
    ],
    "performance": [
        "No N+1 queries",
        "Indexes on all filtered/joined columns",
        "No blocking I/O in async context",
        "No unbounded queries (missing LIMIT)",
        "Large files/responses streamed, not loaded into memory",
    ],
    "tests": [
        "New code has tests",
        "Tests cover the error paths, not just happy path",
        "Tests are readable: clear name, single assertion, no logic",
        "No new skip marks or xfail without explanation",
    ],
    "maintainability": [
        "Variable and function names are self-documenting",
        "Complex logic has a comment explaining *why*, not *what*",
        "No dead code (commented-out blocks, unused imports)",
        "Follows existing conventions in the file",
        "No TODO/FIXME without a ticket number",
    ],
}
