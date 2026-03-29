"""
Integration skill: Transactional email and SMS patterns.
Covers template systems, deliverability, compliance (CAN-SPAM, GDPR), and provider integrations.
"""

EMAIL_TEMPLATE_SYSTEM = '''
# ─────────────────────────────────────────────────────────────────────────────
# Database-backed template system (instead of files)
# ─────────────────────────────────────────────────────────────────────────────

from jinja2 import Template
from sqlalchemy import Column, String, Text
from core.database import Base

class EmailTemplate(Base):
    __tablename__ = 'email_templates'

    name = Column(String(100), primary_key=True)  # 'welcome', 'invoice'
    subject = Column(String(255), nullable=False)
    body_html = Column(Text, nullable=False)  # MJML or Handlebars
    body_text = Column(Text, nullable=True)   # Plain text fallback
    version = Column(Integer, default=1)

# Render function
def render_template(name: str, context: dict) -> tuple[str, str]:
    template = db.query(EmailTemplate).get(name)
    if not template:
        raise ValueError(f"Template {name} not found")

    # Jinja2 rendering (autoescapes by default)
    html = Template(template.body_html).render(**context)
    text = Template(template.body_text or '').render(**context) if template.body_text else html_to_text(html)

    return html, text

# Usage in task queue:
async def send_welcome_email(user_id: str):
    user = await db.users.get(user_id)
    html, text = render_template('welcome', {
        'user': user,
        'login_url': f"{settings.APP_URL}/login",
    })

    await email_queue.add('send', {
        'to': user.email,
        'subject': f"Welcome to {settings.APP_NAME}!",
        'html': html,
        'text': text,
        'categories': ['transactional', 'welcome'],
    })
'''

SENDGRID_INTEGRATION = '''
import sendgrid
from sendgrid.helpers.mail import (
    Mail, Email, To, Content,
    TemplateId, Substitution,
    Category, CustomArg,
    SandBoxMode,
)
from sendgrid.helpers.stats import ClickTracking, OpenTracking

sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))

def send_templated_email(to_email: str, template_name: str, context: dict):
    """Send using SendGrid dynamic template (stored in SendGrid, not DB)."""

    mail = Mail(
        from_email=Email('noreply@myapp.com', 'MyApp'),
        to_emails=To(to_email),
    )

    # Dynamic template (create in SendGrid UI)
    mail.template_id = TemplateId(TEMPLATE_IDS[template_name])

    # Substitutions (handlebar variables)
    for key, value in context.items():
        mail.personalizations[0].add_substitution(Substitution(key, str(value)))

    # Categories for analytics
    mail.add_category(Category('transactional'))
    mail.add_category(Category(template_name))

    # Custom args (passed to webhook)
    mail.add_custom_arg(CustomArg('user_id', context.get('user_id')))
    mail.add_custom_arg(CustomArg('template', template_name))

    # Tracking settings
    tracking = ClickTracking(True, True)  # Enable click tracking, plain text
    open_tracking = OpenTracking(True)
    # mail.tracking_settings = ...

    # Sandbox mode (no emails sent) — use for testing
    # mail.mail_settings = MailSettings(sandbox_mode=SandBoxMode(True))

    try:
        response = sg.send(mail)
        if 200 <= response.status_code < 300:
            return {"message_id": response.headers['X-Message-Id']}
        else:
            logger.error(f"SendGrid failed: {response.body}")
            raise Exception(f"SendGrid error: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}", exc_info=e)
        raise

# Webhook handler for events (bounces, spam reports, clicks)
@app.post("/webhooks/sendgrid")
async def sendgrid_webhook(request: Request):
    # Verify signature (SendGrid signs webhooks)
    signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature')
    timestamp = request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp')
    payload = await request.body()

    if not verify_signature(signature, timestamp, payload):
        raise HTTPException(400, "Invalid signature")

    events = await request.json()
    for event in events:
        # Store in DB for analytics / suppression
        await db.email_events.create({
            'event': event['event'],
            'email': event['email'],
            'timestamp': event['timestamp'],
            'sg_message_id': event.get('sg_message_id'),
        })

        # Handle bounces → suppress email
        if event['event'] == 'bounce':
            await db.suppressions.create({
                'email': event['email'],
                'reason': event.get('bounce_category', 'unknown'),
            })

    return {"received": True}
'''

TWILIO_SMS_PATTERNS = '''
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

twilio_client = TwilioClient(
    os.getenv('TWILIO_ACCOUNT_SID'),
    os.getenv('TWILIO_AUTH_TOKEN')
)

def send_sms(to_phone: str, body: str, country: str = 'US'):
    """Send transactional SMS via Twilio."""
    try:
        message = twilio_client.messages.create(
            body=body,
            from_=get_twilio_number(country),  # E.164 format: +15551234567
            to=to_phone,
            status_callback=os.getenv('TWILIO_STATUS_CALLBACK'),  # Delivery webhook
        )
        return {"sid": message.sid, "status": message.status}
    except TwilioRestException as e:
        if e.code == 21211:  # Invalid phone number
            logger.warning(f"Invalid phone {to_phone}")
            raise InvalidPhoneNumberError()
        elif e.code == 21610:  # SMS not allowed to this number (carrier block)
            logger.warning(f"SMS blocked for {to_phone}")
            raise SMSCarrierBlockError()
        else:
            logger.error(f"Twilio error: {e}")
            raise

# Delivery status webhook
@app.post("/webhooks/twilio/sms")
async def twilio_sms_webhook(request: Request):
    # Twilio sends application/x-www-form-urlencoded
    form = await request.form()
    message_sid = form.get('MessageSid')
    status = form.get('MessageStatus')  # queued, sending, sent, delivered, failed, undelivered

    # Update message status in DB
    await db.sms_messages.update(
        filter={'sid': message_sid},
        values={'status': status, 'updated_at': datetime.utcnow()},
    )

    return Response(status_code=200)
'''

MESSAGE_TEMPLATE_VARIABLES = '''
# Variables available in all templates:
- {{ user.first_name }}
- {{ user.last_name }}
- {{ user.email }}
- {{ app_name }} (your company name)
- {{ support_email }}
- {{ unsubscribe_url }} (for marketing emails only)

# Conditional blocks:
{% if user.plan == 'pro' %}
  <p>Thanks for being a Pro member!</p>
{% endif %}

# Loops:
{% for feature in features %}
  <li>{{ feature }}</li>
{% endfor %}

# Filters:
{{ user.created_at | date:"F j, Y" }}
{{ amount | currency:"USD" }}
'''

TRANSACTIONAL_EMAIL_BEST_PRACTICES = [
    "✅ Double opt-in for newsletters / marketing (CAN-SPAM)",
    "✅ Unsubscribe link in every marketing email (not transactional)",
    "✅ Include valid physical mailing address (required by CAN-SPAM)",
    "✅ Set custom return-path for bounce handling (bounces@myapp.com)",
    "✅ Monitor sender reputation (Google Postmaster, Microsoft SNDS)",
    "✅ Rate limit per domain (max 100/hr to same domain to avoid spam folder)",
    "✅ Use dedicated subdomain (noreply.myapp.com) not gmail.com",
    "✅ SPF + DKIM + DMARC configured (authentication)",
    "✅ Test with mail-tester.com before sending (spam score)",
    "✅ Fallback to plain text version if HTML blocked",
    "✅ Mobile-responsive email templates (40%+ read on mobile)",
    "✅ Images hosted on CDN with proper cache headers",
]

COMPLIANCE_REQUIREMENTS = {
    "can_spam": {
        "requirements": [
            "Clear unsubscribe mechanism (working for 30 days)",
            "Valid physical postal address",
            "Accurate 'From' name and email (no misleading)",
            "Subject line not deceptive",
            "Identify advertisement if applicable",
        ],
        "penalties": "$43,792 per violation (per recipient)",
    },
    "gdpr": {
        "requirements": [
            "Consent before sending marketing emails",
            "Right to withdraw consent (unsubscribe)",
            "Store consent record (timestamp, IP, version)",
            "Data processing agreement with email provider",
        ],
        "data_subject_rights": [
            "Access: user can request all emails sent",
            "Deletion: remove from all mailing lists upon request",
        ],
    },
    "tcpa": {
        "sms_consent": "Express written consent for auto-dialed SMS/telemarketing",
        "disclosure": "Msg & data rates may apply",
        "opt_out": "Reply STOP to unsubscribe (must honor within 10 business days)",
        "hours": "Only send 8am-9pm local time (not telemarketing)",
    },
}

DELIVERABILITY_OPTIMIZATION = {
    "spf": {
        "setup": "v=spf1 include:sendgrid.net ~all",
        "purpose": "Authorize SendGrid (or other provider) to send from your domain",
        "verify": "pydnstools or dig TXT example.com",
    },
    "dkim": {
        "setup": "Generate DKIM keys in SendGrid, add CNAME records",
        "purpose": "Cryptographic signature proves email not tampered",
        "verify": "Check Authentication-Results header in received email",
    },
    "dmarc": {
        "setup": """
v=DMARC1; p=none; rua=mailto:reports@myapp.com; ruf=mailto:forensics@myapp.com; fo=1
""",
        "policies": {
            "p=none": "Monitor only (no enforcement)",
            "p=quarantine": "Move to spam if fail",
            "p=reject": "Reject at SMTP",
        },
        "monitoring": "Use dmarcian or postmark dmarc viewer to parse reports",
    },
    "warmup": {
        "new_domain": "Start with 5,000 emails/day, ramp up 2x daily (week 1)",
        "new_sender": "Send from dedicated IP, gradually increase volume",
        "engagement": "Monitor opens/clicks — low engagement hurts reputation",
    },
}

EMAIL_QUEUE_PROCESSING = '''
# Celery task for batch sending
@app.task(bind=True, max_retries=3, default_retry_delay=300)
def send_batch_emails(self, template_name: str, recipient_ids: list[int]):
    """Send email to batch of users (daily digest, newsletter)."""
    # Fetch users
    users = User.query.filter(User.id.in_(recipient_ids)).all()

    # Rate limit: send in batches of 100 with 1s delay
    for i in range(0, len(users), 100):
        batch = users[i:i+100]

        for user in batch:
            try:
                html, text = render_template(template_name, {'user': user})
                sendgrid_send(user.email, subject, html, text)
            except Exception as exc:
                logger.error(f"Failed to send to {user.email}", exc_info=exc)
                # Continue with others, track failures

        # Rate limit between batches
        time.sleep(1)

    return {"sent": len(users), "template": template_name}

# Alternatively: BullMQ with rate limiter
const emailWorker = new Worker('email', async job => {
  if (job.name === 'batch-newsletter') {
    const { userIds } = job.data

    // Process in batches of 100 with 1s delay
    for (let i = 0; i < userIds.length; i += 100) {
      const batch = userIds.slice(i, i + 100)

      await Promise.all(
        batch.map(userId => sendEmailToUser(userId))
      )

      if (i + 100 < userIds.length) {
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    }
  }
}, {
  settings: {
    rateLimiter: {
      max: 100,  // Max 100 jobs/second
      duration: 1,
    },
  },
})
'''

SMS_BEST_PRACTICES = [
    "Use transactional SMS for one-time codes (OTP), alerts, appointment reminders",
    "Avoid marketing SMS (users must opt-in, TCPA restrictions)",
    "Include opt-out in first message (Reply STOP to unsubscribe)",
    "Keep message under 160 characters (SMS limit)",
    "Use alphanumeric sender ID if available (not random number)",
    "Comply with local regulations (EU, India, Brazil have strict rules)",
    "Don't send high-volume at once (avoid carrier filtering)",
    "Monitor delivery rate — carrier blocks if >5% complaint rate",
    "Use Twilio Messaging Service for multiple numbers and smart routing",
    "Test with test credentials before production (Twilio test SID)",
]

TEMPLATE_MANAGEMENT_WORKFLOW = '''
1. Design template (MJML or HTML)
2. Review copy/text (legal compliance)
3. Test rendering (Email on Acid, Litmus) across clients:
   - Gmail, Outlook, Apple Mail, mobile
4. Create in SendGrid (or save to DB)
5. QA: send test email to internal team
6. Production: schedule or trigger
7. Archive old version (keep audit trail)
8. A/B test (SendGrid can split traffic 50/50)
'''

PROVIDER_COMPARISON = {
    "sendgrid": {
        "pricing": "Free 100/day, then $15/mo for 50k, scale pricing",
        "pros": ["Good deliverability", "Webhooks robust", "Dynamic templates"],
        "cons": ["Expensive at scale", "Support can be slow"],
        "api": "Excellent v3 API, Python SDK",
    },
    "mailgun": {
        "pricing": "5k free/mo, then $0.80/1k emails",
        "pros": ["Cheaper at scale", "Good API", "Suppression lists"],
        "cons": ["Free tier limits", "UI less polished"],
    },
    "postmark": {
        "pricing": "Pay-as-you-go $0.10/email, no monthly fee",
        "pros": ["Transaction focus", "Fast delivery", "Great support"],
        "cons": ["No free tier (10 free trial)", "Marketing features limited"],
    },
    "ses": {
        "pricing": "$0.10/1000 emails, very cheap",
        "pros": ["Cheapest", "AWS integration", "High throughput"],
        "cons": ["Harder to set up (domain verification)", "No dynamic templates",
                 "Support limited", "Deliverability requires work"],
    },
    "twilio_sms": {
        "pricing": "$0.0079-0.015/msg US, varies by country",
        "pros": ["Global coverage", "Good API", "Status callbacks"],
        "cons": ["Expensive for high volumes", "Some countries blocked"],
        "alternatives": ["AWS SNS", "MessageBird", "Vonage"],
    },
}

VOID_TRANSACTIONAL_CHECKS = [
    "Your provider is transactional-focused (not just marketing)",
    "Setup dedicated sending domain (not gmail.com)",
    "Configure SPF, DKIM, DMARC before sending >10k/day",
    "Warm up new domain/IP gradually (avoid spam folder)",
    "Keep promotional content out of transactional emails (CAN-SPAM)",
    "Monitor bounce rate (<2% threshold, >5% triggers review)",
    "Suppress hard bounces immediately",
    "Honor unsubscribe within 10 days",
    "Store consent records (timestamp, IP, version) for GDPR",
    "Test email rendering across clients before send",
]

EMAIL_SECURITY = [
    "Use TLS for SMTP (most providers enforce)",
    "Rotate API keys regularly (30-90 days)",
    "Store keys in environment/S3 Secrets Manager (not code)",
    "Restrict API key permissions (send only, not delete lists)",
    "Monitor API usage (alerts on spikes)",
    "Verify webhook signatures (prevent spoofing)",
    "Sanitize template context (prevent template injection)",
    "Rate limit API calls (prevent abuse)",
]
