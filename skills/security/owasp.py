"""
OWASP Top 10 (2021) knowledge base.
Used by SecurityAgent as structured reference data.
"""

OWASP_TOP_10_CHECKS: dict[str, dict] = {
    "A01:2021": {
        "name": "Broken Access Control",
        "description": "Restrictions on authenticated users not enforced",
        "examples": [
            "Accessing other users' data by changing URL params",
            "Missing function-level access control",
            "CORS misconfiguration allowing untrusted origins",
            "Elevation of privilege — acting as admin without being one",
        ],
        "check_for": [
            "Direct object references without ownership check",
            "Missing @require_permission / @login_required decorators",
            "CORS origin set to *",
            "JWT without role claims validated server-side",
        ],
        "cwe_ids": ["CWE-284", "CWE-285", "CWE-639"],
    },
    "A02:2021": {
        "name": "Cryptographic Failures",
        "description": "Sensitive data exposed due to weak or missing encryption",
        "examples": [
            "Passwords stored as MD5 or SHA1",
            "Sensitive data transmitted over HTTP",
            "Hardcoded secrets in source code",
            "Weak RSA key sizes (< 2048 bit)",
        ],
        "check_for": [
            r"md5|sha1\(password",
            "http:// for API calls in production",
            r"SECRET\s*=\s*['\"][^'\"]{1,20}['\"]",
            "ssl_verify=False or verify=False in requests",
        ],
        "cwe_ids": ["CWE-259", "CWE-327", "CWE-331"],
    },
    "A03:2021": {
        "name": "Injection",
        "description": "User-controlled data sent to an interpreter (SQL, shell, LDAP, etc.)",
        "examples": [
            "f-string SQL queries with user input",
            "subprocess with shell=True and user data",
            "eval() or exec() on user input",
            "Template injection in Jinja2/Mako",
        ],
        "check_for": [
            r"execute\(f['\"]",
            "shell=True",
            r"eval\(.*request",
            r"render_template_string\(.*request",
        ],
        "cwe_ids": ["CWE-89", "CWE-77", "CWE-78"],
    },
    "A04:2021": {
        "name": "Insecure Design",
        "description": "Missing or ineffective security controls at the design level",
        "examples": [
            "No rate limiting on auth endpoints",
            "Security questions as second factor",
            "Unlimited failed login attempts",
            "No CSRF protection on state-changing endpoints",
        ],
        "check_for": [
            "No rate limiter on /login, /register, /reset-password",
            "No CSRF token in forms",
            "No account lockout logic",
        ],
        "cwe_ids": ["CWE-73", "CWE-656"],
    },
    "A05:2021": {
        "name": "Security Misconfiguration",
        "description": "Missing hardening, permissive config, verbose errors",
        "examples": [
            "DEBUG=True in production",
            "Default credentials not changed",
            "Unnecessary features enabled (admin panel, directory listing)",
            "Verbose error messages exposing stack traces",
        ],
        "check_for": [
            r"DEBUG\s*=\s*True",
            "app.run(debug=True)",
            "expose_headers: '*'",
            "allow_origins: ['*']",
        ],
        "cwe_ids": ["CWE-16", "CWE-2"],
    },
    "A06:2021": {
        "name": "Vulnerable and Outdated Components",
        "description": "Using components with known vulnerabilities",
        "examples": [
            "PyJWT < 2.4.0 (algorithm confusion)",
            "Django < 4.2.x (SQL injection)",
            "requests < 2.20.0 (SSRF)",
        ],
        "check_for": [
            "requirements.txt / package.json with pinned old versions",
            "No dependency update policy",
        ],
        "cwe_ids": ["CWE-1104"],
    },
    "A07:2021": {
        "name": "Identification and Authentication Failures",
        "description": "Weak auth implementation",
        "examples": [
            "JWT with alg: none accepted",
            "Weak password policy (< 8 chars)",
            "Session tokens not rotated after login",
            "Password reset tokens not expiring",
        ],
        "check_for": [
            'algorithms=["none"]',
            "jwt.decode without verify=True",
            "No password length/complexity check",
            "Token expiry not set",
        ],
        "cwe_ids": ["CWE-287", "CWE-384", "CWE-521"],
    },
    "A08:2021": {
        "name": "Software and Data Integrity Failures",
        "description": "Code and infra not protected against integrity violations",
        "examples": [
            "Unsigned npm packages",
            "CI/CD pipeline accepting unverified input",
            "Pickle deserialization of untrusted data",
            "Insecure deserialization",
        ],
        "check_for": [
            r"pickle\.loads\(",
            r"yaml\.load\(",          # without Loader
            "eval(base64.b64decode",
        ],
        "cwe_ids": ["CWE-494", "CWE-829"],
    },
    "A09:2021": {
        "name": "Security Logging and Monitoring Failures",
        "description": "Insufficient logging of security events",
        "examples": [
            "Login failures not logged",
            "No alerting on repeated failures",
            "Logs containing passwords or tokens",
            "No audit trail for admin actions",
        ],
        "check_for": [
            "No logging on authentication paths",
            "Log statements containing 'password' variable",
        ],
        "cwe_ids": ["CWE-778", "CWE-223"],
    },
    "A10:2021": {
        "name": "Server-Side Request Forgery (SSRF)",
        "description": "Server fetching user-controlled URLs",
        "examples": [
            "requests.get(user_provided_url) without allowlist",
            "Fetching webhook URLs without validation",
            "Image proxy without URL validation",
        ],
        "check_for": [
            r"requests\.(get|post)\(.*request\.",
            r"httpx\.(get|post)\(.*params\[",
            "urllib.request.urlopen(user_input",
        ],
        "cwe_ids": ["CWE-918"],
    },
}
