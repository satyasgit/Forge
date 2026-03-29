"""
Enterprise skill: SAML 2.0 and OIDC single sign-on (SSO) patterns.
Covers IdP integration, Just-In-Time provisioning, and security best practices.
"""

SAML_CONFIGURATION = '''
# Python: pysaml2
# Node: passport-saml or @auth0/passport-saml

# ─────────────────────────────────────────────────────────────────────────────
# IdP (Identity Provider) Metadata
# ─────────────────────────────────────────────────────────────────────────────
# Enterprise customer provides their IdP metadata (XML)
IDP_METADATA_XML = """
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://okta-abcdefgh123456.okta.com/app/your-app-id/sso/saml">
  <IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <KeyDescriptor use="signing">
      <KeyInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
        <X509Data>
          <X509Certificate>MIID...AB</X509Certificate>
        </X509Data>
      </KeyInfo>
    </KeyDescriptor>
    <SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://okta-abcdefgh123456.okta.com/app/your-app-id/sso/saml"/>
    <SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://okta-abcdefgh123456.okta.com/app/your-app-id/slo/saml"/>
  </IDPSSODescriptor>
</EntityDescriptor>
"""

# ─────────────────────────────────────────────────────────────────────────────
# SP (Service Provider) Settings
# ─────────────────────────────────────────────────────────────────────────────
SP_SETTINGS = {
    "entity_id": "https://myapp.com/saml/metadata",  # Unique identifier for your app
    "assertion_consumer_service_url": "https://myapp.com/saml/acs",
    "single_logout_service_url": "https://myapp.com/saml/slo",
    "x509cert": "-----BEGIN CERTIFICATE-----\nYOUR_SP_CERT\n-----END CERTIFICATE-----",
    "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_SP_KEY\n-----END PRIVATE KEY-----",
    # For testing, generate self-signed: openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365
}

# ─────────────────────────────────────────────────────────────────────────────
# SAML Flow
# ─────────────────────────────────────────────────────────────────────────────
FLOW_DIAGRAM = """
┌─────────┐                                 ┌────────────┐
│  User   │                                 │   IdP      │
│ (Browser)│                                 │ (Okta/Azure│
└────┬────┘                                 └─────┬──────┘
     │ 1. Click "Login with SSO"               │
     │─────────────────────────────────────────>│
     │                                          │
     │ 2. Redirect to IdP with SAMLRequest     │
     │<─────────────────────────────────────────│
     │                                          │ User authenticates
     │                                          │ (SSO session, MFA if needed)
     │                                          │
     │ 3. IdP POSTs SAMLResponse to ACS URL    │
     │─────────────────────────────────────────>│
     │                                          │
     │ 4. Validate signature, extract attrs     │
     │                                          │
     │ 5. Create/lookup user, set session      │
     │                                          │
     │ 6. Redirect to dashboard                │
     │<─────────────────────────────────────────│
"""

# ─────────────────────────────────────────────────────────────────────────────
# Python Implementation (pysaml2)
# ─────────────────────────────────────────────────────────────────────────────
from saml2 import BINDING_HTTP_REDIRECT, BINDING_HTTP_POST
from saml2.client import Saml2Client
from saml2.config import Config

def init_saml_client():
    """Initialize SAML client with IdP metadata."""
    settings = {
        'entityid': SP_SETTINGS['entity_id'],
        'service': {
            'sp': {
                'endpoints': {
                    'assertion_consumer_service': [
                        (SP_SETTINGS['assertion_consumer_service_url'], BINDING_HTTP_POST)
                    ],
                    'single_logout_service': [
                        (SP_SETTINGS['single_logout_service_url'], BINDING_HTTP_REDIRECT)
                    ],
                },
                'name_id_format': 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
                'authn_requests_signed': True,
                'logout_requests_signed': True,
                'want_assertions_signed': True,
                'want_response_signed': True,
            },
        },
        'key_file': '/path/to/sp.key',
        'cert_file': '/path/to/sp.crt',
        'metadata': {
            'remote': [{'url': 'https://idp.example.com/metadata'}],
        },
        'debug': 1,
    }

    config = Config()
    config.load(settings)
    return Saml2Client(config)

# Login endpoint
@app.get("/saml/login")
async def saml_login(request: Request):
    client = init_saml_client()
    # Generate SAML request, redirect to IdP
    req_id, info = client.prepare_for_authenticate()

    # Store req_id in session to validate response
    request.session['saml_request_id'] = req_id

    redirect_url = info['headers'][0][1]  # Location header
    return RedirectResponse(url=redirect_url)

# Assertion Consumer Service (ACS) — IdP POSTs here
@app.post("/saml/acs")
async def saml_acs(request: Request):
    client = init_saml_client()

    # Parse SAML response from POST body
    form = await request.form()
    saml_response = form.get('SAMLResponse')
    if not saml_response:
        raise HTTPException(400, "Missing SAMLResponse")

    # Decode and validate
    try:
        authn_response = client.parse_authn_request_response(
            saml_response,
            binding=BINDING_HTTP_POST
        )
    except Exception as e:
        logger.error(f"SAML validation failed: {e}")
        raise HTTPException(400, "Invalid SAML response")

    # Validate Audience (must match your SP entity_id)
    if authn_response.audience() != SP_SETTINGS['entity_id']:
        raise HTTPException(400, "Audience mismatch")

    # Extract attributes
    attributes = authn_response.get_identity()
    email = attributes.get('email')[0]
    first_name = attributes.get('firstName', [''])[0]
    last_name = attributes.get('lastName', [''])[0]
    tenant_id = attributes.get('tenantId', [None])[0]  # Custom attribute

    # Get or create user
    user = await get_or_create_user_from_saml(email, first_name, last_name, tenant_id)

    # Create session
    token = create_access_token(user.id)
    request.session['access_token'] = token

    return RedirectResponse(url="/dashboard")
'''

SAML_ATTRIBUTE_MAPPING = '''
# IdP sends attributes, map to your user model
# Common attributes (may vary by IdP):

ATTRIBUTE_MAP = {
    'Name ID': 'email',  # Subject (NameID) is usually email
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress': 'email',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname': 'first_name',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname': 'last_name',
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name': 'full_name',
    'http://schemas.microsoft.com/identity/claims/objectidentifier': 'azure_object_id',
    'http://schemas.xmlsoap.org/claims/Group': 'groups',  # Group membership
    'tenantId': 'tenant_id',  # Custom attribute for multi-tenancy
}

# Salesforce attributes example:
# "https://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
# "https://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"

def map_saml_attributes(saml_attrs: dict) -> dict:
    """Map IdP attribute names to internal user fields."""
    user_data = {}
    for saml_attr, internal_field in ATTRIBUTE_MAP.items():
        if saml_attr in saml_attrs and saml_attrs[saml_attr]:
            user_data[internal_field] = saml_attrs[saml_attr][0]
    return user_data
'''

JUST_IN_TIME_PROVISIONING = '''
# Auto-create user on first SSO login
async def get_or_create_user_from_saml(
    email: str,
    first_name: str,
    last_name: str,
    tenant_id: str = None
) -> User:
    # Try to find existing user by email
    user = await db.users.get_by_email(email)
    if user:
        # Update name if changed
        if user.first_name != first_name or user.last_name != last_name:
            user.first_name = first_name
            user.last_name = last_name
            await db.save(user)
        return user

    # New user — create account
    user = await db.users.create({
        'email': email,
        'first_name': first_name,
        'last_name': last_name,
        'tenant_id': tenant_id,
        'auth_provider': 'saml',
        'is_active': True,  # Auto-activate for SSO users
        'password_hash': None,  # No password (SSO only)
    })

    # Assign default role
    await db.user_roles.create(user_id=user.id, role='member')

    # Audit log
    await audit_log(
        action='user.created_via_saml',
        resource_type='User',
        resource_id=user.id
    )

    # Send welcome email
    await email_queue.add('welcome', {'user_id': user.id})

    return user
'''

SAML_LOGOUT = '''
# Single Logout (SLO) — log user out of both SP and IdP

@app.get("/saml/logout")
async def saml_logout(request: Request):
    """Initiate logout request to IdP."""
    client = init_saml_client()

    # Generate logout request
    logout_request = client.prepare_for_logout(
        name_id=request.session.get('saml_name_id'),
        session_index=request.session.get('saml_session_index'),
    )

    # Clear local session
    request.session.clear()

    # Redirect to IdP logout endpoint
    redirect_url = logout_request['url']
    return RedirectResponse(url=redirect_url)

@app.post("/saml/slo")
async def saml_slo(request: Request):
    """Handle logout response from IdP."""
    client = init_saml_client()
    form = await request.form()
    saml_response = form.get('SAMLResponse')

    try:
        client.parse_logout_request_response(saml_response)
    except Exception as e:
        logger.error(f"SLO failed: {e}")

    # User logged out of IdP and SP
    return RedirectResponse(url="/")
'''

SECURITY_BEST_PRACTICES = [
    "✅ Validate Audience (aud) and Recipient (Recipient) in assertion",
    "✅ Validate NotBefore and NotOnOrAfter (prevent replay with old assertion)",
    "✅ Validate XML signature against IdP certificate (use pyXMLSecurity lib)",
    "✅ Require SignedAssertions (not just signed Response)",
    "✅ Use HTTPS everywhere (SAML assertions often not encrypted)",
    "✅ Match NameID to user.email (or configured identifier)",
    "✅ Check destination URL matches your ACS endpoint (prevent misdelivery)",
    "✅ Store IdP metadata separately per tenant (different enterprises use different IdPs)",
    "✅ Fallback to local auth if tenant SSO not configured",
    "✅ Set short session duration (15-30min) and refresh via SAML",
    "✅ Log all SAML failures (invalid signature, expired assertion) with IP",
]

OIDC_ALTERNATIVE = '''
# OIDC (OpenID Connect) is JSON-based, simpler than SAML
# Use if enterprise only needs OIDC (not full SAML)

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name='okta',
    client_id=os.getenv('OKTA_CLIENT_ID'),
    client_secret=os.getenv('OKTA_CLIENT_SECRET'),
    server_metadata_url='https://dev-123.okta.com/oauth2/default/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid profile email'},
)

# Redirect
@app.get("/login/okta")
async def login_okta(request: Request):
    redirect_uri = request.url_for('auth_callback')
    return await oauth.okta.authorize_redirect(request, redirect_uri)

# Callback
@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.okta.authorize_access_token(request)
    user_info = await oauth.okta.parse_id_token(request, token)
    # user_info: {'sub': '123', 'email': '...', 'name': '...'}
    user = await get_or_create_user_from_oidc(user_info)
    create_session(user)
    return RedirectResponse(url="/dashboard")

# OIDC advantages over SAML:
# - JSON (not XML) — easier to parse
# - Built on OAuth 2.0 — standard auth framework
# - Better for mobile apps (native OIDC libraries)
# - Discovery via .well-known/openid-configuration
'''

SAML_VS_OIDC_COMPARISON = {
    "saml": {
        "format": "XML",
        "complexity": "Higher (XML signatures, metadata)",
        "maturity": "Enterprise standard since 2005",
        "use_cases": ["Enterprise SSO", "Government", "Healthcare (HIPAA)", "Legacy IdPs"],
    },
    "oidc": {
        "format": "JSON/REST",
        "complexity": "Lower (OAuth 2.0 extensions)",
        "maturity": "Modern (2014), mobile-friendly",
        "use_cases": ["Modern cloud apps", "Mobile apps", "SPA/React", "API auth"],
    },
}

TROUBLESHOOTING = {
    "common_errors": {
        "Invalid signature": "SP certificate doesn't match IdP metadata or clock skew",
        "Audience mismatch": "Audience in assertion != SP entity_id — check SP settings in IdP",
        "NameID not found": "IdP NameID format different — configure NameID format in SP",
        "Expired assertion": "Clock skew > 5min — sync NTP on servers",
        "Attribute not found": "Attribute names differ by IdP — map correctly",
    },
    "debugging_tools": [
        "SAML tracer (Firefox/Chrome extension) — inspect SAMLRequest/Response",
        "Decode base64 SAMLResponse ( https://www.samltool.com/decode.php )",
        "Enable pysaml2 logging (debug=1)",
        "Test IdP metadata: `samltool.com/validate_metadata`",
    ],
}

MULTI_IDP_SUPPORT = '''
# Support multiple IdPs per tenant (different companies have different IdPs)
TENANT_IDPS = {
    'tenant_abc': {
        'idp_entity_id': 'https://okta.com/abc',
        'metadata_url': 'https://okta.com/abc/metadata',
        'x509cert': '...',
    },
    'tenant_xyz': {
        'idp_entity_id': 'https://azure.com/xyz',
        'metadata_url': None,
        'metadata_xml': '...',  # Or fetch from Entra ID
    },
}

@app.get("/saml/login")
async def saml_login(request: Request):
    tenant_id = request.state.tenant_id
    idp_config = TENANT_IDPS[tenant_id]

    client = Saml2Client(config=build_config(idp_config, tenant_id))
    # ... rest same
'''

IMPLEMENTATION_CHECKLIST = [
    "✅ Obtain SP certificate (self-signed or CA-signed)",
    "✅ Configure SP settings in IdP (ACS URL, entity ID, certificate)",
    "✅ Fetch IdP metadata (XML) and store securely",
    "✅ Implement /saml/login, /saml/acs, /saml/logout endpoints",
    "✅ Validate signature, audience, timestamps on every assertion",
    "✅ Map SAML attributes to user fields",
    "✅ Implement JIT provisioning (create user on first login)",
    "✅ Test with IdP: authenticate, check attributes, session creation",
    "✅ Enable IdP-initiated SSO (user starts from IdP dashboard)",
    "✅ Implement single logout (SLO) if IdP supports",
    "✅ Set up logging for SAML failures (signature, expiry, audience)",
    "✅ Document attribute mapping per enterprise customer",
    "✅ Support multiple IdPs (store per tenant, switch based on tenant)",
    "✅ Fallback to local auth for non-SSO users (mix auth methods)",
]
