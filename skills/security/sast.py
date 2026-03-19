"""
SAST (Static Analysis Security Testing) pattern library.
These regex patterns are run locally by SecurityAgent before the Claude API call,
so the AI gets pre-flagged findings to validate and expand on.
"""

SAST_PATTERNS: list[dict] = [
    # ── Injection ──────────────────────────────────────────────────────────────
    {
        "name": "SQL Injection — f-string query",
        "regex": r'execute\s*\(\s*f["\'].*\{',
        "severity": "critical",
        "owasp_id": "A03:2021",
        "description": "User input interpolated directly into SQL query via f-string.",
        "remediation": "Use parameterised queries: cursor.execute('SELECT * FROM t WHERE id=?', (user_id,))",
        "fix_example": "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
        "languages": ["python"],
    },
    {
        "name": "SQL Injection — string concatenation",
        "regex": r'execute\s*\(\s*["\'].*["\'\s]\s*\+\s*\w',
        "severity": "critical",
        "owasp_id": "A03:2021",
        "description": "SQL query built with string concatenation — allows SQL injection.",
        "remediation": "Always use parameterised queries or an ORM.",
        "fix_example": "cursor.execute('SELECT * FROM users WHERE name = %s', (name,))",
        "languages": ["python"],
    },
    {
        "name": "Command Injection — shell=True",
        "regex": r'subprocess\.(run|call|Popen|check_output).*shell\s*=\s*True',
        "severity": "critical",
        "owasp_id": "A03:2021",
        "description": "subprocess with shell=True and user data allows OS command injection.",
        "remediation": "Pass arguments as a list, never as a string. Never use shell=True with user input.",
        "fix_example": "subprocess.run(['ls', '-la', safe_path], shell=False, capture_output=True)",
        "languages": ["python"],
    },
    {
        "name": "Command Injection — os.system",
        "regex": r'os\.system\s*\(',
        "severity": "high",
        "owasp_id": "A03:2021",
        "description": "os.system executes a shell command. If user input is involved, command injection is possible.",
        "remediation": "Replace with subprocess.run(['cmd', arg1, arg2], shell=False).",
        "fix_example": "result = subprocess.run(['grep', pattern, filepath], capture_output=True, text=True)",
        "languages": ["python"],
    },
    {
        "name": "Eval on user input",
        "regex": r'eval\s*\(\s*(request\.|input\(|params|body)',
        "severity": "critical",
        "owasp_id": "A03:2021",
        "description": "eval() on user-controlled data allows arbitrary code execution.",
        "remediation": "Never use eval() with user input. Use ast.literal_eval() for safe Python literals only.",
        "fix_example": "import ast\nvalue = ast.literal_eval(user_input)  # only for dicts/lists/strings",
        "languages": ["python"],
    },

    # ── Cryptographic Failures ─────────────────────────────────────────────────
    {
        "name": "Weak hash — MD5 for passwords",
        "regex": r'md5\s*\(',
        "severity": "high",
        "owasp_id": "A02:2021",
        "description": "MD5 is cryptographically broken. Never use for passwords or security-sensitive data.",
        "remediation": "Use bcrypt, argon2, or scrypt for password hashing.",
        "fix_example": "from passlib.hash import argon2\nhashed = argon2.hash(password)\nargon2.verify(password, hashed)",
        "languages": ["python"],
    },
    {
        "name": "Weak hash — SHA1 for passwords",
        "regex": r'sha1\s*\(',
        "severity": "high",
        "owasp_id": "A02:2021",
        "description": "SHA1 is deprecated and vulnerable to collision attacks.",
        "remediation": "Use SHA-256 minimum for non-password hashing; use bcrypt/argon2 for passwords.",
        "fix_example": "import hashlib\nhash = hashlib.sha256(data.encode()).hexdigest()",
        "languages": ["python"],
    },
    {
        "name": "SSL verification disabled",
        "regex": r'verify\s*=\s*False',
        "severity": "high",
        "owasp_id": "A02:2021",
        "description": "Disabling SSL verification allows man-in-the-middle attacks.",
        "remediation": "Remove verify=False. If using self-signed cert, pass the CA bundle path instead.",
        "fix_example": "response = requests.get(url, verify='/path/to/ca-bundle.crt')",
        "languages": ["python"],
    },

    # ── Auth Failures ─────────────────────────────────────────────────────────
    {
        "name": "JWT — algorithm none accepted",
        "regex": r'algorithms\s*=\s*\[["\']none["\']',
        "severity": "critical",
        "owasp_id": "A07:2021",
        "description": "Accepting 'none' algorithm allows attackers to forge JWT tokens without a signature.",
        "remediation": "Always specify allowed algorithms explicitly and exclude 'none'.",
        "fix_example": "jwt.decode(token, SECRET_KEY, algorithms=['HS256'])",
        "languages": ["python"],
    },
    {
        "name": "JWT — no expiry set",
        "regex": r'jwt\.encode\(.*\{[^}]*(?!exp)[^}]*\}',
        "severity": "medium",
        "owasp_id": "A07:2021",
        "description": "JWT without 'exp' claim never expires — stolen tokens are valid forever.",
        "remediation": "Always include exp claim. Typical: 15min for access tokens, 7 days for refresh.",
        "fix_example": (
            "from datetime import datetime, timedelta\n"
            "payload = {'user_id': uid, 'exp': datetime.utcnow() + timedelta(minutes=15)}\n"
            "token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')"
        ),
        "languages": ["python"],
    },

    # ── Security Misconfiguration ─────────────────────────────────────────────
    {
        "name": "Debug mode in production",
        "regex": r'DEBUG\s*=\s*True|app\.run\(.*debug\s*=\s*True',
        "severity": "high",
        "owasp_id": "A05:2021",
        "description": "Debug mode exposes stack traces, environment variables, and interactive debugger.",
        "remediation": "Set DEBUG=False in production. Use environment variable: DEBUG=os.getenv('DEBUG', False).",
        "fix_example": "DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'",
        "languages": ["python"],
    },
    {
        "name": "CORS wildcard origin",
        "regex": r'allow_origins\s*=\s*\[\s*["\'][*]["\']',
        "severity": "high",
        "owasp_id": "A05:2021",
        "description": "CORS wildcard allows any origin to make cross-origin requests — enables CSRF.",
        "remediation": "Specify exact allowed origins. Use environment variable for flexibility.",
        "fix_example": (
            "from fastapi.middleware.cors import CORSMiddleware\n"
            "app.add_middleware(CORSMiddleware,\n"
            "    allow_origins=settings.ALLOWED_ORIGINS,  # ['https://app.yourdomain.com']\n"
            "    allow_credentials=True, allow_methods=['*'], allow_headers=['*'])"
        ),
        "languages": ["python"],
    },

    # ── Insecure Deserialization ──────────────────────────────────────────────
    {
        "name": "Insecure pickle deserialization",
        "regex": r'pickle\.loads?\s*\(',
        "severity": "critical",
        "owasp_id": "A08:2021",
        "description": "pickle.loads() on untrusted data allows arbitrary code execution.",
        "remediation": "Never deserialize pickle from untrusted sources. Use JSON or MessagePack instead.",
        "fix_example": "import json\ndata = json.loads(trusted_json_string)",
        "languages": ["python"],
    },
    {
        "name": "Unsafe YAML load",
        "regex": r'yaml\.load\s*\([^,)]+\)',
        "severity": "high",
        "owasp_id": "A08:2021",
        "description": "yaml.load() without Loader can execute arbitrary Python via YAML tags.",
        "remediation": "Always use yaml.safe_load() for untrusted input.",
        "fix_example": "import yaml\ndata = yaml.safe_load(stream)",
        "languages": ["python"],
    },

    # ── Path Traversal ────────────────────────────────────────────────────────
    {
        "name": "Path traversal risk",
        "regex": r'open\s*\(\s*(request\.|params|body|\w+\[)',
        "severity": "high",
        "owasp_id": "A01:2021",
        "description": "File open with user-controlled path allows reading arbitrary files (../../etc/passwd).",
        "remediation": "Validate and sanitize paths. Use pathlib and restrict to an allowed directory.",
        "fix_example": (
            "from pathlib import Path\n"
            "BASE_DIR = Path('/safe/upload/dir')\n"
            "safe_path = (BASE_DIR / user_filename).resolve()\n"
            "if not safe_path.is_relative_to(BASE_DIR):\n"
            "    raise ValueError('Path traversal detected')\n"
            "with open(safe_path) as f: ..."
        ),
        "languages": ["python"],
    },

    # ── SSRF ──────────────────────────────────────────────────────────────────
    {
        "name": "SSRF — unvalidated URL fetch",
        "regex": r'(requests|httpx)\.(get|post)\s*\(\s*(request\.|params|body|\w+\[)',
        "severity": "high",
        "owasp_id": "A10:2021",
        "description": "Fetching user-provided URL allows server-side request forgery to internal services.",
        "remediation": "Validate URLs against an allowlist of domains. Block internal IP ranges.",
        "fix_example": (
            "from urllib.parse import urlparse\n"
            "ALLOWED_HOSTS = {'api.trusted.com', 'hooks.trusted.com'}\n"
            "parsed = urlparse(user_url)\n"
            "if parsed.hostname not in ALLOWED_HOSTS:\n"
            "    raise ValueError('URL not in allowlist')\n"
            "response = requests.get(user_url, timeout=5)"
        ),
        "languages": ["python"],
    },

    # ── XSS ───────────────────────────────────────────────────────────────────
    {
        "name": "Reflected XSS — user input in HTML response",
        "regex": r'return.*HTMLResponse.*\{.*request\.',
        "severity": "high",
        "owasp_id": "A03:2021",
        "description": "User input rendered directly in HTML response enables reflected XSS.",
        "remediation": "Use template engine with auto-escaping (Jinja2 with autoescape=True). Never concatenate user input into HTML.",
        "fix_example": (
            "from markupsafe import escape\n"
            "safe_q = escape(user_query)\n"
            "return HTMLResponse(f'<h1>Results for {safe_q}</h1>')"
        ),
        "languages": ["python"],
    },

    # ── Mass Assignment ───────────────────────────────────────────────────────
    {
        "name": "Mass assignment — model(**request.dict())",
        "regex": r'\w+\(\*\*(request|data|body)\.dict\(\)',
        "severity": "medium",
        "owasp_id": "A01:2021",
        "description": "Passing full request dict to model constructor allows overwriting protected fields (is_admin, role).",
        "remediation": "Explicitly specify allowed fields. Use a separate input schema without privileged fields.",
        "fix_example": (
            "# Don't: User(**request.dict())\n"
            "# Do:\n"
            "user = User(\n"
            "    email=request.email,\n"
            "    name=request.name,\n"
            "    # is_admin NOT included — must be set separately with auth check\n"
            ")"
        ),
        "languages": ["python"],
    },
]
