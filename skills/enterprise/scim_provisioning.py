"""
Enterprise skill: SCIM 2.0 provisioning system.
Covers User/Group CRUD, PATCH operations, and synchronization with enterprise IdPs (Okta, Azure AD).
"""

SCIM_ENDPOINTS = '''
# SCIM 2.0 REST API specification
# Standardized user/group provisioning from enterprise IdPs

# Base path: /scim/v2

# ─────────────────────────────────────────────────────────────────────────────
# Service Provider Configuration (discovery)
# ─────────────────────────────────────────────────────────────────────────────
GET /ServiceProviderConfig
Response:
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
  "patch": {"supported": true},
  "bulk": {"supported": false, "maxOperations": 100},
  "filter": {"supported": true, "maxResults": 200},
  "changePassword": {"supported": false},
  "sort": {"supported": false},
  "etag": {"supported": false},
  "authenticationSchemes": [
    {
      "name": "Bearer",
      "description": "Bearer token authentication",
      "specUri": "https://tools.ietf.org/html/rfc6750",
      "type": "bearer"
    }
  ]
}

# ─────────────────────────────────────────────────────────────────────────────
# Users Endpoint
# ─────────────────────────────────────────────────────────────────────────────
GET    /Users                    # List users (filterable, paginated)
POST   /Users                    # Create user
GET    /Users/{id}               # Get user by SCIM ID
PUT    /Users/{id}               # Replace user (full update)
PATCH  /Users/{id}               # Partial update (op: add/remove/replace)
DELETE /Users/{id}               # Deactivate user (soft delete)

# ─────────────────────────────────────────────────────────────────────────────
# Groups Endpoint
# ─────────────────────────────────────────────────────────────────────────────
GET    /Groups
POST   /Groups
GET    /Groups/{id}
PUT    /Groups/{id}
PATCH  /Groups/{id}
DELETE /Groups/{id}

# ─────────────────────────────────────────────────────────────────────────────
# Bulk Operations (optional)
# ─────────────────────────────────────────────────────────────────────────────
POST /Bulk
'''

SCIM_USER_SCHEMA = '''
# SCIM core user schema (urn:ietf:params:scim:schemas:core:2.0:User)
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "id": "abc123-def456",
  "userName": "john.doe@acmecorp.com",
  "name": {
    "givenName": "John",
    "familyName": "Doe",
    "middleName": ""
  },
  "displayName": "John Doe",
  "emails": [
    {
      "value": "john.doe@acmecorp.com",
      "primary": true,
      "type": "work"
    },
    {
      "value": "john.doe@gmail.com",
      "primary": false,
      "type": "personal"
    }
  ],
  "active": true,
  "timezone": "America/New_York",
  "locale": "en-US",
  "preferredLanguage": "en",
  "phoneNumbers": [
    {
      "value": "+1-555-123-4567",
      "primary": true,
      "type": "work"
    }
  ],
  "addresses": [
    {
      "formatted": "123 Main St, Anytown, CA 12345",
      "locality": "Anytown",
      "region": "CA",
      "postalCode": "12345",
      "country": "US"
    }
  ],
  "externalId": "okta-uid-12345",  # IdP's user ID (store for sync)
  "groups": [
    {"value": "group-id-123", "$ref": "/Groups/group-id-123"}
  ],
  "meta": {
    "resourceType": "User",
    "created": "2024-01-01T00:00:00Z",
    "lastModified": "2024-01-01T00:00:00Z"
  }
}

# Enterprise extensions (vendor-specific)
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:company:schemas:custom:user"
  ],
  "customField1": "value",
  "employeeId": "EMP-12345"
}
'''

SCIM_IMPLEMENTATION = '''
from fastapi import APIRouter, Body, HTTPException, Header, Depends, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional, Any, Dict
import uuid

router = APIRouter(prefix="/scim/v2", tags=["scim"])

# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
class ScimEmail(BaseModel):
    value: EmailStr
    primary: bool = True
    type: str = "work"

class ScimName(BaseModel):
    givenName: str
    familyName: str
    middleName: Optional[str] = None

class ScimUser(BaseModel):
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:User"]
    userName: EmailStr
    name: ScimName
    displayName: Optional[str] = None
    emails: List[ScimEmail] = []
    active: bool = True
    externalId: Optional[str] = None  # IdP's user ID
    groups: List[Dict[str, str]] = []  # [{"value": "group-id", "$ref": "/Groups/id"}]
    # Enterprise extension fields
    employeeId: Optional[str] = None
    department: Optional[str] = None

    @field_validator('userName')
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip()

class ScimUserUpdate(BaseModel):
    schemas: Optional[List[str]] = None
    userName: Optional[EmailStr] = None
    name: Optional[ScimName] = None
    displayName: Optional[str] = None
    emails: Optional[List[ScimEmail]] = None
    active: Optional[bool] = None
    externalId: Optional[str] = None
    groups: Optional[List[Dict[str, str]]] = None

# ─────────────────────────────────────────────────────────────────────────────
# Helper: SCIM error responses
# ─────────────────────────────────────────────────────────────────────────────
def scim_error(status: int, detail: str, schemas: List[str] = None):
    return JSONResponse(
        status_code=status,
        content={
            "schemas": schemas or ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": str(status),
            "detail": detail,
        }
    )

# ─────────────────────────────────────────────────────────────────────────────
# Middleware: Bearer token auth for SCIM endpoints
# ─────────────────────────────────────────────────────────────────────────────
async def verify_scim_auth(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    if token != os.getenv('SCIM_API_TOKEN'):
        raise HTTPException(401, "Invalid SCIM token")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# List users with pagination and filtering
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/Users")
async def list_users(
    start_index: int = 1,
    count: int = 100,
    filter: Optional[str] = None,
    attributes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(User)

    if filter:
        if 'userName eq' in filter:
            email = filter.split('"')[1]
            query = query.filter(User.email == email)

    total = query.count()
    users = query.offset(start_index - 1).limit(count).all()

    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(users),
        "Resources": [user.to_scim(attributes) for user in users],
    }

# ─────────────────────────────────────────────────────────────────────────────
# Create user (JIT provisioning)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/Users")
async def create_user(
    user_data: ScimUser,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_scim_auth)
):
    if user_data.externalId:
        existing = db.query(User).filter_by(external_id=user_data.externalId).first()
        if existing:
            return scim_error(409, "User with externalId already exists")

    existing = db.query(User).filter_by(email=user_data.userName).first()
    if existing:
        existing.first_name = user_data.name.givenName
        existing.last_name = user_data.name.familyName
        existing.external_id = user_data.externalId
        existing.is_active = user_data.active
        db.commit()
        return existing.to_scim()

    user = User(
        id=str(uuid.uuid4()),
        email=user_data.userName,
        first_name=user_data.name.givenName,
        last_name=user_data.name.familyName,
        external_id=user_data.externalId,
        is_active=user_data.active,
        tenant_id=get_tenant_id_from_request(request),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    await audit_log(
        action='user.created_via_scim',
        resource_type='User',
        resource_id=user.id
    )

    return user.to_scim()

@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    attributes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    user = db.query(User).get(user_id)
    if not user:
        return scim_error(404, "User not found")
    return user.to_scim(attributes)

@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    user_data: ScimUser,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_scim_auth)
):
    user = db.query(User).get(user_id)
    if not user:
        return scim_error(404, "User not found")

    user.email = user_data.userName
    user.first_name = user_data.name.givenName
    user.last_name = user_data.name.familyName
    user.external_id = user_data.externalId
    user.is_active = user_data.active
    db.commit()
    return user.to_scim()

@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    patch_data: dict = Body(...),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_scim_auth)
):
    user = db.query(User).get(user_id)
    if not user:
        return scim_error(404, "User not found")

    operations = patch_data.get("Operations", [])
    for op in operations:
        operation = op["op"]
        path = op.get("path")
        value = op.get("value")
        apply_patch_operation(user, operation, path, value)

    db.commit()
    return user.to_scim()

def apply_patch_operation(user: User, op: str, path: Optional[str], value: Any):
    if path is None:
        return
    parts = path.split('.')
    for i, part in enumerate(parts[:-1]):
        if '[' in part:
            field_name, _ = part.split('[', 1)
            collection = getattr(user, field_name, [])
        else:
            pass
    last_part = parts[-1]
    if op in ("replace", "add"):
        setattr(user, last_part, value)

@router.delete("/Users/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_scim_auth)
):
    user = db.query(User).get(user_id)
    if not user:
        return scim_error(404, "User not found")
    user.is_active = False
    db.commit()
    return Response(status_code=204)
'''

GROUP_SYNC_PATTERNS = '''
# Groups for RBAC — keep Okta/Azure AD groups in sync with app roles

class ScimGroup(BaseModel):
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:Group"]
    displayName: str
    members: List[Dict[str, str]] = []

@router.post("/Groups")
async def create_group(group: ScimGroup, db: Session = Depends(get_db)):
    role = await db.roles.create(
        name=group.displayName,
        scim_group_id=group.id if hasattr(group, 'id') else None
    )
    return role.to_scim()

@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: str,
    patch_data: dict,
    db: Session = Depends(get_db)
):
    role = db.query(Role).get(group_id)
    if not role:
        return scim_error(404, "Group not found")

    for op in patch_data.get("Operations", []):
        if op["op"] == "add":
            user_id = op["value"]["value"]
            await add_user_to_role(user_id, role.id)
        elif op["op"] == "remove":
            user_id = op["value"]["value"]
            await remove_user_from_role(user_id, role.id)

    return role.to_scim()
'''

PUSH_PROVISIONING_FLOW = '''
# Enterprise sends push notifications when user CRUD happens

# POST /scim/v2/Users              (user added)
# PATCH /scim/v2/Users/{id}        (user updated)
# DELETE /scim/v2/Users/{id}       (user deprovisioned)

# Response must be IMMEDIATE (< 5s) or IdP retries
@app.post("/scim/v2/Users")
async def create_user(request: Request, user_data: ScimUser = Body(...)):
    user = User.create(...)
    # Async: allocate licenses, send welcome, add to teams
    await background_tasks.add_task(provision_user_resources, user.id)
    return user.to_scim()
'''

ERROR_HANDLING = '''
# SCIM-compliant error responses

HTTP 200: Success
HTTP 201: Created
HTTP 204: No Content
HTTP 400: Bad Request
HTTP 401: Unauthorized
HTTP 403: Forbidden
HTTP 404: Not Found
HTTP 409: Conflict (duplicate resource)
HTTP 424: Failed Dependency (retry later)
HTTP 429: Too Many Requests

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
  "status": "400",
  "detail": "Invalid filter syntax"
}
'''

RATE_LIMITING = '''
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@router.post("/Users")
@limiter.limit("100/minute;500/hour")
async def create_user(...):
    ...
'''

TESTING_SCIM = '''
# Test with:
# 1. Okta SCIM test tool
# 2. Azure AD SCIM test utility
# 3. Postman collection for SCIM

def test_user_crud():
    # POST → 201
    # GET → same data
    # PATCH → update verified
    # DELETE → 204, deactivated
'''

IMPLEMENTATION_CHECKLIST = [
    "✅ Choose SCIM library (pyscitools, scim2) or custom implementation",
    "✅ Implement /ServiceProviderConfig discovery endpoint",
    "✅ Implement /Users CRUD with pagination, filtering",
    "✅ Implement /Groups CRUD for RBAC sync",
    "✅ Support PATCH operations (add/remove/replace)",
    "✅ Implement Bearer token auth for SCIM endpoints",
    "✅ Handle SCIM errors with proper HTTP status codes",
    "✅ Store externalId (IdP's user ID) for idempotency",
    "✅ Test with enterprise IdP (Okta, Azure AD, OneLogin)",
    "✅ Set up rate limiting per tenant/IP",
    "✅ Background async processing (license allocation, emails)",
    "✅ Audit log all SCIM operations",
    "✅ Handle bulk operations if needed (POST /Bulk)",
    "✅ Implement filtering (userName eq, active eq)",
    "✅ Support custom enterprise schemas (extensions)",
    "✅ Document attribute mapping for each customer",
    "✅ Test idempotency (repeated requests produce same result)",
]
