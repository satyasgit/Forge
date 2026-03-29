"""
Security Agent — fully working OWASP-based security review agent.

Capabilities:
  - OWASP Top 10 (2021) analysis
  - Dependency vulnerability scanning (pip-audit / npm audit)
  - Secret / credential leak detection
  - SAST pattern matching (SQLi, XSS, path traversal, etc.)
  - JWT / auth flow audit
  - Infrastructure-as-code security (Docker, GitHub Actions)
  - Threat model generation
  - Remediation recommendations with code examples

Usage:
    from agents.security_agent import SecurityAgent

    agent = SecurityAgent(project_id="my-project")
    result = agent.run_full_audit(
        code={"auth.py": "...", "routes.py": "..."},
        language="python",
        context="FastAPI SaaS app with JWT auth and Stripe billing"
    )
    print(result.output)
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from agents.base import BaseAgent, AgentResult
from skills.security.owasp import OWASP_TOP_10_CHECKS
from skills.security.sast import SAST_PATTERNS
from skills.security.threat_model import THREAT_MODEL_TEMPLATE


@dataclass
class SecurityFinding:
    owasp_id: str          # e.g. "A03:2021"
    owasp_name: str        # e.g. "Injection"
    severity: str          # critical | high | medium | low | info
    title: str
    description: str
    location: str          # file:line or "architecture"
    evidence: str          # the offending code snippet
    remediation: str       # plain-language fix
    code_fix: str          # actual fixed code example
    cve_refs: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        cves = ", ".join(self.cve_refs) if self.cve_refs else "N/A"
        return textwrap.dedent(f"""
            ### [{self.severity.upper()}] {self.title}
            **OWASP:** {self.owasp_id} — {self.owasp_name}
            **Location:** `{self.location}`
            **CVE refs:** {cves}

            **Finding:**
            {self.description}

            **Evidence:**
            ```
            {self.evidence}
            ```

            **Remediation:**
            {self.remediation}

            **Fixed code:**
            ```python
            {self.code_fix}
            ```
        """).strip()


from agents.agent_config import register_agent

@register_agent
class SecurityAgent(BaseAgent):
    name = "security"
    role = "Application Security Engineer"
    enabled_tools = ["github_get_file", "run_command"]

    @property
    def system_prompt(self) -> str:
        owasp_summary = "\n".join(
            f"- {k}: {v['name']} — {v['description']}"
            for k, v in OWASP_TOP_10_CHECKS.items()
        )
        sast_patterns = "\n".join(
            f"- {p['name']}: `{p['pattern']}` ({p['severity']})"
            for p in SAST_PATTERNS[:10]
        )
        return textwrap.dedent(f"""
            You are a senior application security engineer with 15+ years of experience.
            You specialise in: OWASP Top 10, SAST/DAST, cloud security, and secure SDLC.

            ## OWASP Top 10 (2021) you check against:
            {owasp_summary}

            ## SAST patterns you scan for:
            {sast_patterns}

            ## Your output format:
            Structure every security review as follows:

            ### EXECUTIVE SUMMARY
            One paragraph. Overall risk posture, most critical finding, immediate action needed.

            ### FINDINGS
            For each finding:
            - **[SEVERITY]** Title (OWASP A0X:2021)
            - Location (file:line)
            - What's wrong
            - Evidence (code snippet)
            - Exact fix with code example

            Severity levels: CRITICAL (fix before deploy) | HIGH (fix this sprint) |
            MEDIUM (fix next sprint) | LOW (backlog) | INFO (best practice)

            ### DEPENDENCY AUDIT
            List vulnerable packages with CVE, current version, and safe version.

            ### SECRETS SCAN
            Report any hardcoded credentials, API keys, tokens, passwords.

            ### ARCHITECTURE RISKS
            Auth design, data flow risks, trust boundary violations.

            ### THREAT MODEL (STRIDE)
            Spoofing | Tampering | Repudiation | Info Disclosure | DoS | Elevation of Privilege

            ### REMEDIATION ROADMAP
            Prioritised list: what to fix immediately vs this sprint vs next sprint.

            ### COMPLIANCE NOTES
            Relevant to: GDPR, SOC 2, PCI-DSS, HIPAA if applicable.

            Be precise. Cite line numbers. Provide working code fixes.
            Never say "consider" — say exactly what to do.
        """).strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run_full_audit(
        self,
        code: dict[str, str],         # {filename: content}
        language: str = "python",
        context: str = "",
        requirements_txt: str = "",
    ) -> AgentResult:
        """Full security audit: SAST + OWASP + secrets + deps + threat model."""

        # 1. Run local SAST scan (fast, no API call)
        static_findings = self._run_sast(code)

        # 2. Run secrets scan
        secret_findings = self._scan_secrets(code)

        # 3. Build the prompt
        code_block = "\n\n".join(
            f"### File: {fname}\n```{language}\n{content}\n```"
            for fname, content in code.items()
        )

        sast_summary = self._format_sast_findings(static_findings + secret_findings)

        deps_section = ""
        if requirements_txt:
            deps_section = f"\n\n### requirements.txt / package.json:\n```\n{requirements_txt}\n```"

        task = textwrap.dedent(f"""
            Perform a comprehensive security audit of this codebase.

            ## Application context
            {context or 'No additional context provided.'}

            ## Code to audit
            {code_block}
            {deps_section}

            ## Pre-computed SAST findings (validate and expand these)
            {sast_summary}

            ## Threat model template to fill
            {THREAT_MODEL_TEMPLATE}

            Produce the full security report as described in your instructions.
            For every finding, provide a working code fix — not pseudocode.
        """).strip()

        return self.run(task)

    def audit_file(self, filename: str, content: str, language: str = "python") -> AgentResult:
        """Audit a single file."""
        return self.run_full_audit({filename: content}, language)

    def audit_github_repo(self, repo: str, files: list[str]) -> AgentResult:
        """Fetch files from GitHub and audit them."""
        code = {}
        for path in files:
            result = self.run(f"Fetch file {path} from repo {repo}")
            code[path] = result.output
        return self.run_full_audit(code, context=f"GitHub repo: {repo}")

    def generate_threat_model(self, architecture_description: str) -> AgentResult:
        """Generate a STRIDE threat model for an architecture."""
        task = textwrap.dedent(f"""
            Generate a comprehensive STRIDE threat model for this architecture:

            {architecture_description}

            For each STRIDE category, list:
            1. Specific threats relevant to this system
            2. Current mitigations (if any apparent)
            3. Recommended controls
            4. Risk score (1-10)

            Then produce a Data Flow Diagram description and trust boundary analysis.
        """)
        return self.run(task)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal SAST scanner (runs locally, no API cost)
    # ──────────────────────────────────────────────────────────────────────────

    def _run_sast(self, code: dict[str, str]) -> list[SecurityFinding]:
        findings = []
        for filename, content in code.items():
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern in SAST_PATTERNS:
                    if re.search(pattern["regex"], line, re.IGNORECASE):
                        findings.append(SecurityFinding(
                            owasp_id=pattern["owasp_id"],
                            owasp_name=OWASP_TOP_10_CHECKS[pattern["owasp_id"]]["name"],
                            severity=pattern["severity"],
                            title=pattern["name"],
                            description=pattern["description"],
                            location=f"{filename}:{i}",
                            evidence=line.strip(),
                            remediation=pattern["remediation"],
                            code_fix=pattern.get("fix_example", ""),
                        ))
        return findings

    def _scan_secrets(self, code: dict[str, str]) -> list[SecurityFinding]:
        SECRET_PATTERNS = [
            (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',     "Hardcoded password"),
            (r'(?i)(api_key|apikey|api-key)\s*=\s*["\'][^"\']{10,}["\']', "Hardcoded API key"),
            (r'(?i)(secret|token)\s*=\s*["\'][^"\']{10,}["\']',           "Hardcoded secret/token"),
            (r'(?i)aws_access_key_id\s*=\s*["\']?[A-Z0-9]{20}',           "AWS Access Key"),
            (r'sk-[a-zA-Z0-9]{48}',                                         "OpenAI API key"),
            (r'(?i)private.?key.{0,20}-----BEGIN',                          "Private key in code"),
            (r'(?i)bearer\s+[a-zA-Z0-9\-._~+/]{20,}',                      "Bearer token in code"),
        ]
        findings = []
        for filename, content in code.items():
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if any(skip in line.lower() for skip in ["example", "placeholder", "your_", "<", "env.", "os.environ"]):
                    continue
                for pattern, label in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append(SecurityFinding(
                            owasp_id="A02:2021",
                            owasp_name="Cryptographic Failures",
                            severity="critical",
                            title=f"Secret in source code: {label}",
                            description=(
                                f"{label} found hardcoded in source. "
                                "This will be exposed in version control and logs."
                            ),
                            location=f"{filename}:{i}",
                            evidence=re.sub(
                                r'(["\'])[^"\']{4,}(["\'])', r'\1***REDACTED***\2', line.strip()
                            ),
                            remediation=(
                                "Move to environment variable. "
                                "Rotate the credential immediately if already committed."
                            ),
                            code_fix=(
                                "import os\n"
                                f"value = os.environ['{label.upper().replace(' ', '_')}']"
                            ),
                        ))
        return findings

    def _format_sast_findings(self, findings: list[SecurityFinding]) -> str:
        if not findings:
            return "No static findings from local scan."
        lines = [f"Found {len(findings)} static findings:"]
        for f in findings:
            lines.append(f"  - [{f.severity.upper()}] {f.title} at {f.location}")
        return "\n".join(lines)


# ─── Run standalone ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Example: audit a vulnerable FastAPI snippet
    SAMPLE_CODE = {
        "auth.py": '''
import sqlite3
import jwt
from fastapi import APIRouter

SECRET = "mysecretkey123"
router = APIRouter()

@router.post("/login")
def login(username: str, password: str):
    conn = sqlite3.connect("users.db")
    # BUG: SQL injection
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    user = conn.execute(query).fetchone()
    if user:
        token = jwt.encode({"user": username}, SECRET, algorithm="HS256")
        return {"token": token}
    return {"error": "Invalid credentials"}
''',
        "routes.py": '''
from fastapi import APIRouter
import subprocess

router = APIRouter()

@router.get("/files")
def get_file(path: str):
    # BUG: Path traversal + command injection
    result = subprocess.run(f"cat {path}", shell=True, capture_output=True)
    return {"content": result.stdout.decode()}

@router.get("/search")
def search(q: str):
    # BUG: Reflected XSS (in a template context)
    return {"html": f"<h1>Results for {q}</h1>"}
''',
    }

    agent = SecurityAgent(project_id="demo-project")
    result = agent.run_full_audit(
        code=SAMPLE_CODE,
        language="python",
        context="FastAPI web app with user authentication and file serving",
        requirements_txt="fastapi==0.100.0\npyjwt==1.7.1\nsqlite3",
    )
    print(result.output)
    print(f"\n--- Cost: ${result.cost_usd:.4f} | Time: {result.duration_seconds:.1f}s ---")
