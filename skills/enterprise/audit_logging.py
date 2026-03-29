"""
Enterprise skill: Structured audit logging patterns for compliance (SOC 2, GDPR, HIPAA).
Covers immutable audit trails, who-did-what, change tracking, and retention policies.
"""

AUDIT_LOG_MODEL = '''
# Semantic Audit Logging pattern — immutable record of all important actions
from sqlalchemy import Column, String, JSON, DateTime, Enum as SQLEnum, Boolean, Text
from sqlalchemy.sql import func
from core.database import Base
import uuid

class AuditLog(Base):
    __tablename__ = 'audit_logs'

    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # When
    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True  # Queries by date range
    )

    # Who
    user_id = Column(String(36), nullable=False, index=True)
    # Optional: store full user snapshot for historical records (in case user deleted/renamed)
    user_snapshot = Column(JSON, nullable=True)  # {'email': ..., 'name': ..., 'roles': [...]}

    # What
    action = Column(String(100), nullable=False, index=True)  # e.g., 'user.created', 'subscription.cancelled'
    resource_type = Column(String(50), nullable=False, index=True)  # 'User', 'Invoice', 'Team'
    resource_id = Column(String(36), nullable=False, index=True)  # UUID of affected resource

    # Before/After state (for updates)
    old_values = Column(JSON, nullable=True)   # Pre-update state (for UPDATE)
    new_values = Column(JSON, nullable=True)   # Post-update state (for CREATE/UPDATE)

    # Context
    ip_address = Column(String(45), nullable=True, index=True)  # IPv6 max 45
    user_agent = Column(String(500), nullable=True)
    correlation_id = Column(String(36), nullable=True, index=True)  # Trace across services

    # Metadata
    metadata_ = Column('metadata', JSON, nullable=True)  # Extra context: request_id, session_id

    __table_args__ = (
        # Composite index for common query: "show all changes to a resource"
        Index('ix_audit_resource_timestamp', 'resource_type', 'resource_id', 'timestamp'),
        # Partial index for recent logs (PostgreSQL) — optional performance tweak:
        # Index('ix_audit_recent', 'timestamp', postgresql_using='btree', postgresql_where='timestamp > NOW() - INTERVAL \\'90 days\\''),
    )
'''

AUDIT_DECORATOR_PATTERN = '''
from functools import wraps
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from fastapi import Request, Depends
from core.database import get_db
from core.auth import get_current_user_id

def audit_log(
    action: str,
    resource_type: str,
    include_old_state: bool = False,
    exclude_fields: list[str] = None  # e.g., ['password_hash']
):
    """
    Decorator to automatically create audit log entries.
    Works with FastAPI route handlers.
    """
    exclude_fields = exclude_fields or ['password', 'password_hash', 'token', 'secret']

    def decorator(func):
        @wraps(func)
        async def wrapper(
            *args,
            request: Request = None,
            db: Session = Depends(get_db),
            current_user_id: str = Depends(get_current_user_id),
            **kwargs
        ):
            # 1. Extract resource ID from kwargs (assume 'id' param or resource object)
            resource_id = kwargs.get('id')
            resource_obj = kwargs.get('resource') or kwargs.get('obj')

            # 2. If update operation, capture old state before calling function
            old_values = None
            if include_old_state and resource_obj is not None:
                old_values = {}
                state = inspect(resource_obj).attrs
                for attr in state:
                    if attr.key not in exclude_fields:
                        old_values[attr.key] = attr.value

            # 3. Call the original function
            result = await func(*args, db=db, current_user_id=current_user_id, **kwargs)

            # 4. Extract new state from result (assume result is ORM object)
            new_values = None
            if hasattr(result, '__dict__'):
                new_values = {}
                for key, value in result.__dict__.items():
                    if key not in exclude_fields and not key.startswith('_'):
                        new_values[key] = value

            # 5. Create audit log (only if state changed)
            if old_values or new_values:
                # Determine if it's create, update, or delete
                if old_values is None:
                    action_suffix = 'created'
                elif new_values is None or (hasattr(result, '__deleted__') and result.__deleted__):
                    action_suffix = 'deleted'
                else:
                    action_suffix = 'updated'

                full_action = f"{resource_type.lower()}.{action_suffix}"

                audit = AuditLog(
                    user_id=current_user_id,
                    action=full_action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else str(result.id),
                    old_values=old_values,
                    new_values=new_values,
                    ip_address=request.client.host if request else None,
                    user_agent=request.headers.get('user-agent') if request else None,
                    correlation_id=getattr(request.state, 'correlation_id', None),
                )
                db.add(audit)
                # Commit inside try-except to avoid losing audit log
                try:
                    await db.commit()
                except Exception as e:
                    logger.error(f"Failed to write audit log: {e}", exc_info=True)
                    # Don't fail the request if audit fails

            return result

        @wraps(wrapper)
        async def inner(*args, **kwargs):
            return await wrapper(*args, **kwargs)
        return inner
    return decorator

# Usage:
@router.delete("/users/{user_id}")
@audit_log(action="delete", resource_type="User", include_old_state=True)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    user = await db.users.get(user_id)
    user.__deleted__ = True  # Mark as deleted for decorator
    await db.delete(user)
    await db.commit()
    return {"status": "deleted"}
'''

AUDIT_QUERY_PATTERNS = '''
from sqlalchemy import select, and_, between
from datetime import date, datetime, timedelta

class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_timeline(
        self,
        user_id: str,
        start: date,
        end: date,
        limit: int = 100
    ) -> list[AuditLog]:
        """Timeline of all actions by a specific user."""
        return self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.timestamp.between(
                        datetime.combine(start, datetime.min.time()),
                        datetime.combine(end, datetime.max.time())
                    )
                )
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        ).scalars().all()

    def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50
    ) -> list[AuditLog]:
        """Full change history of a specific resource (reconstruct state)."""
        return self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.resource_type == resource_type,
                    Audi tLog.resource_id == resource_id
                )
            )
            .order_by(AuditLog.timestamp.asc())
            .limit(limit)
        ).scalars().all()

    def search_by_ip(
        self,
        ip_address: str,
        start: datetime = None,
        limit: int = 100
    ) -> list[AuditLog]:
        """Security investigation: what actions came from this IP?"""
        query = select(AuditLog).where(AuditLog.ip_address == ip_address)
        if start:
            query = query.where(AuditLog.timestamp >= start)
        return self.db.execute(
            query.order_by(AuditLog.timestamp.desc()).limit(limit)
        ).scalars().all()

    def get_changes_for_field(
        self,
        resource_type: str,
        resource_id: str,
        field_name: str
    ) -> list[tuple[datetime, Any, Any]]:
        """Track changes to a specific field (e.g., user.email changes)."""
        logs = self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.resource_type == resource_type,
                    AuditLog.resource_id == resource_id,
                    AuditLog.old_values.isnot(None),  # Only updates
                )
            )
            .order_by(AuditLog.timestamp.asc())
        ).scalars().all()

        changes = []
        for log in logs:
            if field_name in log.old_values and field_name in log.new_values:
                if log.old_values[field_name] != log.new_values[field_name]:
                    changes.append((
                        log.timestamp,
                        log.old_values[field_name],
                        log.new_values[field_name],
                    ))
        return changes

    def rebuild_resource_state(
        self,
        resource_type: str,
        resource_id: str
    ) -> dict:
        """Reconstruct entire resource state by applying audit log (for forensic analysis)."""
        logs = self.get_resource_history(resource_type, resource_id)

        # Find the CREATE log (first entry)
        create_log = logs[0]  # Assuming ordered asc
        current_state = create_log.new_values.copy() if create_log.new_values else {}

        # Apply each UPDATE
        for log in logs[1:]:
            if log.old_values and log.new_values:
                for key, new_val in log.new_values.items():
                    if key not in log.old_values or log.old_values[key] != new_val:
                        current_state[key] = new_val
                # Handle deleted fields
                for key in log.old_values:
                    if key not in log.new_values:
                        current_state.pop(key, None)

        return current_state

    def filter_by_action(
        self,
        action_pattern: str,
        start: datetime,
        end: datetime
    ) -> list[AuditLog]:
        """Find all actions matching pattern (e.g., 'user.%', 'subscription.cancel%')."""
        return self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.action.like(action_pattern),
                    AuditLog.timestamp.between(start, end)
                )
            )
            .order_by(AuditLog.timestamp.desc())
        ).scalars().all()

    def export_csv(
        self,
        start: datetime,
        end: datetime,
        resource_type: str = None
    ) -> str:
        """Export audit logs as CSV (for compliance requests)."""
        import csv
        import io

        query = select(AuditLog).where(
            AuditLog.timestamp.between(start, end)
        )
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)

        logs = self.db.execute(query.order_by(AuditLog.timestamp.asc())).scalars().all()

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'id', 'timestamp', 'user_id', 'action', 'resource_type', 'resource_id',
            'ip_address', 'old_values', 'new_values'
        ])
        writer.writeheader()
        for log in logs:
            writer.writerow({
                'id': log.id,
                'timestamp': log.timestamp.isoformat(),
                'user_id': log.user_id,
                'action': log.action,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'ip_address': log.ip_address,
                'old_values': json.dumps(log.old_values) if log.old_values else '',
                'new_values': json.dumps(log.new_values) if log.new_values else '',
            })

        return output.getvalue()
'''

COMPLIANCE_RETENTION_POLICIES = '''
# Audit log retention based on compliance framework

import logging
from datetime import datetime, timedelta
from sqlalchemy import delete

RETENTION_POLICIES = {
    'gdpr': {
        'description': 'EU General Data Protection Regulation',
        'audit_logs': '5 years from log date (Article 30)',
        'legal_basis': 'Statute of limitations for administrative fines (5 years)',
        'auto_delete': 'DELETE FROM audit_logs WHERE timestamp < NOW() - INTERVAL \\'5 years\\'',
    },
    'soc2': {
        'description': 'AICPA Service Organization Control 2',
        'audit_logs': '7 years minimum (WORM storage recommended)',
        'legal_basis': 'Audit trail retention for evidence',
        'auto_delete': 'Archive to S3 Glacier after 3 years, delete after 7',
    },
    'hipaa': {
        'description': 'Health Insurance Portability and Accountability Act',
        'audit_logs': '6 years from creation (45 CFR § 164.316)',
        'legal_basis': 'Documentation retention requirement',
        'auto_delete': '6 years',
    },
    'pci_dss': {
        'description': 'Payment Card Industry Data Security Standard',
        'audit_logs': '1 year minimum (12 months)',
        'legal_basis': 'Requirement 10.5.2',
        'auto_delete': 'After 1 year, unless under investigation',
    },
}

def auto_prune_audit_logs(db: Session, retention_days: int):
    """
    Background task to delete old audit logs.
    Run monthly via cron.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Count before deletion (for metrics)
    count_query = select(func.count()).select_from(AuditLog).where(
        AuditLog.timestamp < cutoff_date
    )
    total = db.execute(count_query).scalar()

    if total > 0:
        logger.info(f"Pruning {total} audit log entries older than {cutoff_date}")

        # Delete in batches to avoid lock
        batch_size = 10000
        while True:
            # Get IDs to delete
            ids_query = select(AuditLog.id).where(
                AuditLog.timestamp < cutoff_date
            ).limit(batch_size)
            ids = db.execute(ids_query).scalars().all()

            if not ids:
                break

            # Delete by ID (fast with PK)
            db.execute(
                delete(AuditLog).where(AuditLog.id.in_(ids))
            )
            db.commit()
            logger.info(f"Deleted {len(ids)} audit logs")

    return {"deleted": total, "cutoff": cutoff_date.isoformat()}

# Celery task:
@celery.task
def prune_audit_logs_monthly():
    """Run first of every month."""
    from core.config import settings
    auto_prune_audit_logs(get_db(), settings.AUDIT_LOG_RETENTION_DAYS)
'''

IMMUTABILITY_AND_INTEGRITY = '''
# Ensure audit logs cannot be modified or deleted (except by retention job)

# 1. Database-level protection (PostgreSQL)
CREATE POLICY prevent_delete_update ON audit_logs
  USING (false)  -- Block all DELETE and UPDATE
  WITH CHECK (false);

-- Allow retention job to run as superuser or via SECURITY DEFINER function

# 2. Application-level: Set DB user to read-only for this table
# In SQLAlchemy:
class AuditLog(Base):
    __table_args__ = {
        'sqlite_autoincrement': True,  # Prevent ORM from updating PK
    }

# 3. Hash chain for tamper detection (optional):
# Store SHA256 hash of previous log entry in each row (blockchain-like)
class AuditLog(Base):
    ...
    previous_hash = Column(String(64), nullable=True)
    current_hash = Column(String(64), nullable=False)

    def compute_hash(self):
        import hashlib
        payload = f"{self.timestamp}|{self.user_id}|{self.action}|...|{self.previous_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

# On insert:
new_log.previous_hash = latest_log.current_hash
new_log.current_hash = new_log.compute_hash()

# Verify chain periodically:
SELECT id, previous_hash, current_hash FROM audit_logs ORDER BY timestamp;
-- Check: previous_hash of row N == current_hash of row N-1
'''

AUDIT_LOG_GOVERNANCE = {
    "who_can_view": [
        "Compliance officers (read-only)",
        "Security team (incident investigation)",
        "Auditors (external, temporary access)",
        "Legal (with approval)",
        "NOT developers (except debugging own actions)",
    ],
    "access_control": """
-- Database role:
GRANT SELECT ON audit_logs TO compliance_role;
GRANT SELECT ON audit_logs TO security_role;
DENY ALL ON audit_logs TO developer_role;
""",
    "encryption": [
        "Encrypt at rest (PostgreSQL pgcrypto or disk-level encryption)",
        "TLS in transit for DB connections",
        "Consider field-level encryption for highly sensitive data (IP addresses)",
    ],
    "export_requests": [
        "GDPR Subject Access Request (SAR) — provide all audit logs for user",
        "Automated export endpoint: GET /api/audit/export?user_id=xxx",
        "Format: JSON or CSV, include metadata explaining columns",
        "Review before release (redact other users' data if needed)",
    ],
    "monitoring": [
        "Alert on deletion attempts (should never happen)",
        "Alert on bulk reads (>100k rows by single user)",
        "Track growth rate per month (capacity planning)",
        "Track query performance (slow queries > 1s)",
    ],
}

AUDIT_LOG_INTEGRATION_WITH_LOGGING = '''
# Complement structured audit logs with application logs:

# AuditLog table: "WHO did WHAT to WHOM, WHEN" (immutable, searchable, for compliance)
# Application logs: "SYSTEM events, errors, debug info" (ephemeral, for debugging)

# Example: User login
# 1. AuditLog entry (persisted):
action='user.login', resource_type='User', resource_id=user.id, ip_address=..., user_id=user.id

# 2. Application log (structured JSON):
{"level": "INFO", "event": "login", "user_id": "abc", "ip": "1.2.3.4", "user_agent": "..."}

# Relationship: both have correlation_id, user_id, timestamp
# Audit log is authoritative for compliance; app logs are for operations/debug

# Correlation ID pattern:
import uuid
correlation_id = request.state.correlation_id = str(uuid.uuid4())
# Set in middleware, passed to all logs and audit entries
'''

PRIVACY_ANONYMIZATION = '''
# GDPR Right to be Forgotten: anonymize audit logs after retention period

def anonymize_audit_log(user_id: str, db: Session):
    """
    Anonymize all audit log entries created by a user (for GDPR deletion request).
    Keep the log entries (compliance requires them), but remove PII.
    """
    # Find all logs by this user (not about this user)
    logs = db.query(AuditLog).filter(AuditLog.user_id == user_id).all()

    for log in logs:
        # Anonymize user identifier (but keep internal ID for chain of custody)
        log.user_id = f"anonymized-{log.user_id[:8]}"  # Or replace with hash

        # Potentially anonymize IP (GDPR considers IP PII)
        log.ip_address = None

        # If user_snapshot contains PII, wipe it
        if log.user_snapshot:
            log.user_snapshot = {
                k: "***" for k in log.user_snapshot.keys()
            }

    db.commit()
    return len(logs)

# Run after user deletion (right to erasure, but audit retains for compliance)
'''

IMPLEMENTATION_CHECKLIST = [
    "✅ Create AuditLog model with all fields + indexes",
    "✅ Write Alembic migration (add table)",
    "✅ Implement @audit_log decorator (or middleware for CRUD)",
    "✅ Setup retention policy cron job (monthly prune)",
    "✅ Configure DB permissions (read-only for non-compliance roles)",
    "✅ Add audit log export endpoint (GDPR SAR)",
    "✅ Set up monitoring (growth rate, query perf, deletion attempts)",
    "✅ Document retention policies per compliance framework (SOC2, GDPR, HIPAA)",
    "✅ Train team on what actions should be audited (don't over-audit)",
    "✅ Test tamper detection (if using hash chain)",
    "✅ Implement anonymization procedure for GDPR deletion requests",
    "✅ Backup audit logs separately (for disaster recovery)",
]

AUDIT_WHAT_TO_LOG = {
    "critical_always": [
        "User authentication events (login, logout, MFA, password change)",
        "Authorization failures (access denied)",
        "Data export requests (GDPR SAR)",
        "Data deletion requests (GDPR erasure)",
        "Privilege escalation (role changes)",
        "Configuration changes (system settings, webhooks)",
        "Billing events (subscription created/cancelled, invoice paid)",
        "API credential creation/deletion (API keys, webhook secrets)",
    ],
    "important_most_cases": [
        "CRUD operations on sensitive entities (User, Invoice, Payment, Team)",
        "File uploads/downloads (especially PII)",
        "Third-party integrations enabled/disabled",
        "Export data (CSV, PDF)",
        "Admin actions (impersonation, bulk operations)",
    ],
    "maybe": [
        "Page views (too noisy)",
        "Read-only access to non-sensitive data",
        "Failed login attempts (but log in separate security log)",
    ],
    "never_log": [
        "Passwords (plaintext or hashed)",
        "API secrets, webhook signatures",
        "PII in full (collect minimal, encrypt if needed)",
        "Credit card numbers (PCI scope — never store raw)",
    ],
}
