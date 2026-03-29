"""
Integration skill: Message queues for async processing (Celery Python, Bull Node.js).
Covers task design, retry patterns, idempotency, dead letter queues, and monitoring.
"""

QUEUE_DESIGN_PRINCIPLES = {
    "idempotency": {
        "definition": "Task must produce same result if executed multiple times (retry safe)",
        "implementation": '''
# Python (Celery): Use unique task ID + check if already processed
@celery.task(bind=True, name='process_payment')
def process_payment(self, payment_id: str, user_id: str):
    # Check if already processed (atomic DB check or Redis lock)
    if redis.get(f"payment:{payment_id}:processed"):
        return {"status": "already_done"}

    # Process payment
    result = payment_service.charge(payment_id, user_id)

    # Mark as done (set lock)
    redis.setex(f"payment:{payment_id}:processed", 86400, "1")

    return result
''',
        "node_bull": '''
// Use job ID as idempotency key
await emailQueue.add('send-welcome', { userId }, {
  jobId: `welcome:${userId}`,  // Same job ID for same user → deduped
  removeOnComplete: 100,
  attempts: 3,
})
''',
    },
    "failure_handling": {
        "description": "Max retries → dead letter queue (DLQ) for manual review",
        "python_celery": '''
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, user_id: str, template: str):
    try:
        user = User.objects.get(id=user_id)
        email_service.send(user.email, template)
    except (SMTPException, ConnectionError) as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    except Exception as exc:
        # Non-retryable error → log + alert
        logger.error(f"Failed to send email to {user_id}", exc_info=exc)
        send_alert(f"Email task failed permanently: {exc}")
        raise
''',
        "node_bull": '''
const worker = new Worker('email', async job => {
  try {
    await emailService.send(job.data.userId, job.data.template)
  } catch (err) {
    if (err.isRetryable) {
      throw err  // Bull retries automatically
    } else {
      // Move to delayed queue for manual review
      await failedQueue.add('email-failed', job.data, {
        delay: 24 * 60 * 60 * 1000,  // Retry in 24h
      })
      throw err
    }
  }
}, {
  connection: redis,
  settings: {
    maxRetries: 3,
    backoff: {
      type: 'exponential',
      delay: 60000,
    },
  },
})
''',
    },
    "visibility_timeout": {
        "description": "Time after which unacknowledged message becomes visible again (DLQ prevention)",
        "calculation": "Visibility timeout = max_processing_time × 2",
        "example": "Job takes 30s max → visibility timeout = 60s",
        "warning": "Too short → duplicate processing. Too long → slow failure detection.",
    },
    "priority_queues": {
        "recommendation": "Use separate queues instead of priority (Bull priority is per-job)",
        "pattern": '''
# High priority: premium users, critical alerts
email_high = new Queue('email:high', { connection: redis })
email_low = new Queue('email:low', { connection: redis })

# Worker pools: more workers on high queue
new Worker('email:high', highPriorityJob, { ... }, { ... })
new Worker('email:low', lowPriorityJob, { ... }, { ... })
''',
    },
    "monitoring": {
        "metrics": [
            "Queue length (waiting count)",
            "Job processing rate (jobs/sec)",
            "Average job duration",
            "Failed job rate",
            "Worker CPU/memory utilization",
        ],
        "tools": [
            "Bull Board (BullMQ) / Flower (Celery) — web UI",
            "Prometheus metrics via custom exporter",
            "Redis INFO stats for queue internals",
        ],
    },
}

CELERY_PYTHON_PATTERNS = '''
# tasks.py
from celery import Celery
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

app = Celery('tasks')
app.config_from_object('celeryconfig')

@app.task(
    bind=True,  # Gives access to self.request.retries, etc.
    name='send_welcome_email',
    autoretry_for=(SMTPException, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    retry_backoff=True,  # Exponential backoff: 60s, 120s, 240s
    acks_late=True,  # Only ACK after task completes (not on receive)
)
def send_welcome_email(self, user_id: str):
    """Send welcome email to new user (idempotent)."""
    # Idempotency: check if already sent
    cache_key = f"email:welcome:{user_id}"
    if cache.get(cache_key):
        logger.info(f"Welcome email already sent to {user_id}")
        return {"status": "already_sent"}

    user = User.objects.get(id=user_id)
    email.send(
        to=user.email,
        template='welcome',
        context={'name': user.first_name}
    )

    # Mark as sent
    cache.setex(cache_key, 86400, "1")  # 24h TTL

    return {"status": "sent", "to": user.email}

@app.task(name='generate_monthly_report')
def generate_monthly_report(month: str, year: int):
    """Long-running task (2-3min) — run with dedicated worker."""
    report = ReportService().generate(month, year)
    # Upload to S3
    s3_key = f"reports/{year}/{month}/report-{uuid4()}.pdf"
    s3.upload(report.pdf, s3_key)
    return {"s3_key": s3_key}

# Periodic tasks (celery beat)
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Every day at 2am
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        cleanup_old_sessions.s(),
    )

    # Every hour
    sender.add_periodic_task(
        3600.0,
        sync_analytics.s(),
    )

# Celery config (celeryconfig.py)
broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/1'
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

# Task routing (different queues for different workloads)
task_routes = {
    'tasks.send_welcome_email': {'queue': 'email'},
    'tasks.generate_monthly_report': {'queue': 'reports', 'priority': 0},
    'tasks.cleanup_old_sessions': {'queue': 'maintenance'},
}

# Worker concurrency (default = CPU cores × 2)
# I/O bound tasks: increase concurrency (--concurrency=20)
# CPU bound tasks: keep at CPU cores (--concurrency=4)
'''

BULLMQ_NODE_PATTERNS = '''
import { Queue, Worker, Job } from 'bullmq'
import IORedis from 'ioredis'

const connection = new IORedis({
  host: process.env.REDIS_HOST,
  port: 6379,
})

// ── Queue Definition ─────────────────────────────────────────────────────────
const emailQueue = new Queue('email', { connection })
const imageQueue = new Queue('image-processing', { connection })

// ── Adding Jobs ─────────────────────────────────────────────────────────────
async function queueWelcomeEmail(userId: string) {
  await emailQueue.add('send-welcome', { userId }, {
    // Job ID = deduplication key
    jobId: `welcome:${userId}`,
    priority: 1,  // Higher = sooner (0 is highest)
    removeOnComplete: 100,  // Keep last 100 completed in Redis
    removeOnFail: 50,  // Keep last 50 failed
    delay: 5000,  // 5 second delay
    attempts: 3,  // Max retries
    backoff: {
      type: 'exponential',
      delay: 60000,
    },
  })
}

// ── Worker ───────────────────────────────────────────────────────────────────
const emailWorker = new Worker('email', async job => {
  const { userId } = job.data

  if (job.name === 'send-welcome') {
    await emailService.sendWelcome(userId)
  } else if (job.name === 'send-notification') {
    await emailService.sendNotification(userId, job.data.payload)
  }
}, {
  connection,
  concurrency: 10,  // 10 jobs processed in parallel
  settings: {
    stalledInterval: 30000,  // Mark job stalled after 30s
    maxStalledCount: 1,
  },
})

// ── Worker Events ────────────────────────────────────────────────────────────
emailWorker.on('completed', job => {
  console.log(`Job ${job.id} completed`)
})

emailWorker.on('failed', (job, err) => {
  console.error(`Job ${job.id} failed:`, err)
  // Send alert if critical job
  if (job.name === 'payment-confirmation') {
    sendSlackAlert(`Payment job failed: ${job.id}`)
  }
})

emailWorker.on('stalled', job => {
  console.warn(`Job ${job.id} stalled — reassigning`)
})

// ── Job Status Tracking ──────────────────────────────────────────────────────
const job = await emailQueue.getJob('welcome:123')
const state = await job.getState()  // 'completed', 'failed', 'active', 'waiting'
const progress = job.progress  // 0-100
const failedReason = job.failedReason

// ── Queue Inspection ────────────────────────────────────────────────────────
const waitingCount = await emailQueue.getWaitingCount()
const activeCount = await emailQueue.getActiveCount()
const completedCount = await emailQueue.getCompletedCount()
const failedCount = await emailQueue.getFailedCount()

// ── Requeue Failed Jobs ─────────────────────────────────────────────────────
const failedJobs = await emailQueue.getFailed()
for (const job of failedJobs) {
  if (job.failedReason === 'Timeout') {
    await job.retry()  // Re-queue with backoff
  } else {
    await job.moveToFailed('manual-retry')  // Mark for manual review
  }
}

// ── Cleanup ──────────────────────────────────────────────────────────────────
// Clean completed jobs older than 7 days
setInterval(async () => {
  await emailQueue.clean(86400 * 7, 'completed')
  await emailQueue.clean(86400 * 7, 'failed')
}, 3600000)  // Every hour
'''

DELAYED_AND_SCHEDULED_JOBS = '''
# BullMQ delayed tasks
await queue.add('task', data, {
  delay: 60000,  // Execute in 60 seconds
})

# Cron-like recurring jobs (BullMQ Scheduler)
import { QueueScheduler } from 'bullmq'

const scheduler = new QueueScheduler('email', { connection })

// Repeat every day at 9am
await emailQueue.add('daily-report', {}, {
  repeat: {
    cron: '0 9 * * *',  // 9am daily
    tz: 'America/New_York',
  },
})

// Repeat every 5 minutes
await emailQueue.add('sync', {}, {
  repeat: { every: 300000 },  // 5 minutes
})

# Celery beat (periodic tasks)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'cleanup-every-midnight': {
        'task': 'tasks.cleanup_old_sessions',
        'schedule': crontab(hour=0, minute=0),
    },
}
'''

WORKER_DEPLOYMENT = {
    "celery_systemd": '''
# /etc/systemd/system/celery-worker.service
[Unit]
Description=Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=appuser
Group=appuser
WorkingDirectory=/opt/myapp
EnvironmentFile=/opt/myapp/.env
ExecStart=/opt/myapp/venv/bin/celery -A tasks worker --loglevel=info --concurrency=10
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
''',
    "bull_pm2": '''
# ecosystem.config.js
module.exports = {
  apps: [
    {
      name: 'email-worker',
      script: 'workers/email.js',
      instances: 2,  // 2 processes for load balancing
      exec_mode: 'cluster',
      env: { NODE_ENV: 'production', QUEUE: 'email' },
    },
  ],
}
''',
    "kubernetes": '''
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: worker
        image: myapp/worker:latest
        command: ['celery', '-A', 'tasks', 'worker', '--loglevel=info']
        env:
        - name: REDIS_URL
          value: redis://redis-service:6379/0
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
''',
}

ERROR_HANDLING_BEST_PRACTICES = [
    "Retry only transient errors (network, 5xx, rate limits)",
    "Don't retry 4xx errors (bad request) — fail fast",
    "Set max retries to prevent infinite loops (3-5 typical)",
    "Use exponential backoff with jitter to avoid thundering herd",
    "Dead letter queue for manual review after max retries",
    "Alert on DLQ items (PagerDuty/Slack)",
    "Log structured JSON: task_id, args, error_type, retry_count",
    "Monitor failed job rate — spike indicates system issue",
    "Test retry scenarios: simulate DB down, network timeout",
    "Keep tasks atomic — don't break business logic into 10 chained tasks",
]

TASK_DESIGN_GUIDELINES = [
    "Single responsibility: one task does one thing (not 'process_order' + send_email + update_stock)",
    "Idempotent: same inputs → same outcome, safe to retry",
    "Bounded duration: < 1 hour for most tasks (avoid long-running)",
    "Idempotency key: use business ID (user_id + action) as job ID",
    "Avoid shared mutable state: tasks should not depend on global vars",
    "Pass serializable args (JSON, not ORM objects)",
    "Store result only if needed (Celery result_backend optional)",
    "Avoid circular dependencies (Task A → B → A)",
    "Keep task modules small, import dependencies at top (not inside task)",
    "Use separate queues for CPU vs I/O bound tasks (different worker pools)",
]

QUEUE_ANTI_PATTERNS = [
    "❌ Large payloads in Redis (store file IDs, not file contents)",
    "❌ Chained tasks creating dependencies (use workflows or orchestration)",
    "❌ No timeout on jobs (hang forever, block worker)",
    "❌ Ignoring failed jobs (DLQ fills up → no visibility)",
    "❌ Updating DB in many small tasks (batch operations)",
    "❌ Using queue for real-time (use WebSockets instead)",
    "❌ Not monitoring queue depth (backpressure needed)",
    "❌ Shared mutable state between tasks (race conditions)",
    "❌ Long-running tasks in I/O-bound worker pools (mix workloads)",
    "❌ No circuit breaker: keep retrying dead service (wastes resources)",
]

COMPARISON_CELERY_VS_BULL = {
    "celery": {
        "language": "Python only",
        "maturity": "Very mature (since 2009), large community",
        "features": "Periodic tasks, rate limiting, chords, canvas workflows",
        "cons": "Complex config, Django integration quirks, process-based workers",
        "use_when": "Python backend, need advanced workflows (chord, group, chain)",
    },
    "bullmq": {
        "language": "Node.js / TypeScript",
        "maturity": "Modern (Bull v3), well-maintained",
        "features": "Priority, delayed, repeatable, job events, dashboard",
        "cons": "Node only, younger than Celery",
        "use_when": "Node backend, need clean API + monitoring UI",
    },
    "sidekiq": {
        "language": "Ruby",
        "maturity": "Mature, Redis-native",
        "features": "Similar to Bull (jobs, queues, reliability)",
        "use_when": "Ruby backend",
    },
}
