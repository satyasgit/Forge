"""
Integration skill: AWS S3 (and compatible) object storage patterns.
Covers presigned URLs, CDN integration, security best practices, and event notifications.
"""

S3_PRESIGNED_URL_PATTERNS = {
    "upload": {
        "description": "Client uploads directly to S3 without going through backend",
        "flow": """
1. Client requests presigned URL from backend (POST /api/upload-url)
2. Backend generates time-limited PUT URL for S3
3. Client PUTs file directly to S3
4. S3 triggers event (S3:ObjectCreated) → Lambda or notification queue
5. Backend records file metadata in DB
""",
        "python_fastapi": '''
from datetime import timedelta
from botocore.exceptions import ClientError

s3_client = boto3.client('s3')
BUCKET = os.getenv('S3_BUCKET')

@app.post("/api/upload-url")
async def generate_upload_url(
    filename: str,
    content_type: str,
    user_id: str = Depends(get_current_user_id)
):
    # Validate filename (no path traversal, allowed extensions)
    safe_filename = secure_filename(filename)
    key = f"uploads/{user_id}/{uuid4()}-{safe_filename}"

    # Generate presigned URL (expires in 1 hour)
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': BUCKET,
                'Key': key,
                'ContentType': content_type,  # Client must match
                'ACL': 'private',
            },
            ExpiresIn=3600,  # seconds
            HttpMethod='PUT',
        )
    except ClientError as e:
        raise HTTPException(500, "Failed to generate upload URL")

    return {
        "upload_url": url,
        "key": key,
        "expires_in": 3600,
    }

# Client then:
# PUT upload_url with file body + Content-Type header
# On success (200 OK), call backend to record metadata: POST /api/files {key, filename, size}
''',
        "node_express": '''
import AWS from 'aws-sdk'
const s3 = new AWS.S3()

app.post('/api/upload-url', async (req, res) => {
  const { filename, contentType } = req.body
  const key = `uploads/${req.user.id}/${uuidv4()}-${sanitize(filename)}`

  const url = s3.getSignedUrl('putObject', {
    Bucket: process.env.S3_BUCKET,
    Key: key,
    ContentType: contentType,
    Expires: 3600,  // 1 hour
    ACL: 'private',
  })

  res.json({ upload_url: url, key })
})
''',
        "security_considerations": [
            "Validate file extension and MIME type before upload",
            "Set Content-Type in presigned params to prevent content-type sniffing",
            "Use short expiry (1h max, 15min for mobile)",
            "Limit file size via Content-Length on actual upload (S3 max 5TB)",
        ],
    },
    "download": {
        "description": "Presigned GET URL for private files (no public bucket)",
        "use_cases": ["User avatars", "Invoices", "Export files", "Private documents"],
        "python_fastapi": '''
@app.get("/api/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: Session = Depends(get_db)
):
    # Verify user has permission to access file
    file = await db.files.get(file_id)
    if not file or file.user_id != current_user_id:
        raise HTTPException(404, "File not found")

    # Generate presigned GET URL (expires in 15 min)
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': BUCKET,
            'Key': file.s3_key,
        },
        ExpiresIn=900,  // 15 minutes
    )

    return {"download_url": url}
'''
    },
    "thumbnail_generation": {
        "description": "Use Lambda@Edge or CloudFront Functions to generate thumbnails on-the-fly",
        "pattern": """
Store: /uploads/{user}/{uuid}-{filename}.jpg
Serve: https://cdn.example.com/thumb/200x200/uploads/{user}/{filename}.jpg

CloudFront Lambda@Edge:
- Parse URL path for dimensions
- Fetch original from S3
- Resize with Sharp (Node) or Pillow (Python)
- Cache in CloudFront (Cache-Control: max-age=86400)
""",
    },
}

S3_SECURITY_BEST_PRACTICES = [
    "✅ bucket policy: BlockPublicAccess.enforced (block all public access)",
    "✅ Never expose bucket to public unless static website hosting (use CloudFront)",
    "✅ IAM roles over access keys (EC2/ECS/Lambda use instance profiles)",
    "✅ Enable S3 Versioning for backup and rollback",
    "✅ Enable Server-Side Encryption (SSE-S3 or SSE-KMS)",
    "✅ Use S3 Access Points for multi-tenant or different access patterns",
    "✅ CORS configuration for direct browser uploads (only needed origins)",
    "✅ Require TLS (aws:SecureTransport) in bucket policy",
    "✅ S3 Object Lock for WORM (Write Once Read Many) compliance",
    "✅ Lifecycle policies: auto-delete temp files after 7 days",
]

S3_BUCKET_POLICY_EXAMPLE = '''
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::my-bucket/*",
      "Condition": {
        "Bool": { "aws:SecureTransport": "false" }
      }
    },
    {
      "Sid": "DenyPublicAccess",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::my-bucket/*",
      "Condition": {
        "Bool": { "aws:SecureTransport": "false" }
      }
    }
  ]
}
'''

S3_LIFECYCLE_POLICIES = '''
# Transition old files to cheaper storage
# .lifecycle.yml or via AWS Console

Rules:
  - ID: "Move to Infrequent Access after 30 days"
    Status: Enabled
    Filter:
      Prefix: "uploads/"
    Transitions:
      - Days: 30
        StorageClass: STANDARD_IA  # 50% cheaper than standard

  - ID: "Move to Glacier after 90 days"
    Filter:
      Prefix: "uploads/"
    Transitions:
      - Days: 90
        StorageClass: GLACIER_IR  # Instant retrieval Glacier (access within ms)
        # Or GLACIER (7-48h retrieval), DEEP_ARCHIVE (12-48h)

  - ID: "Delete temp files after 7 days"
    Filter:
      Prefix: "temp/"
    Expiration:
      Days: 7

  - ID: "Delete incomplete multipart uploads"
    Status: Enabled
    Filter: {}
    AbortIncompleteMultipartUpload:
      DaysAfterInitiation: 7
'''

CDN_INTEGRATION = '''
# CloudFront + S3: Fast, global delivery + security

# 1. Create CloudFront distribution with S3 as origin
# 2. Set Origin Domain = your-bucket.s3.amazonaws.com
# 3. Origin Protocol Policy = HTTPS Only
# 4. Viewer Protocol Policy = Redirect HTTP to HTTPS
# 5. Configure OAI (Origin Access Identity):
#    - Create OAI in CloudFront
#    - Add S3 bucket policy granting read to OAI
#    - Block public access on bucket (only CloudFront can read)

# 6. Caching behavior:
#    - Default TTL: 86400s (1 day)
#    - Min TTL: 0
#    - Max TTL: 31536000 (1 year)
#    - Forward query strings? Only if needed (breaks cache)

# 7. Custom domain:
#    Add CNAME: cdn.example.com → dxxxxx.cloudfront.net
#    Request ACM certificate for domain (us-east-1)

# 8. Signed URLs (optional, for private content):
import datetime
from botocore.signers import CloudFrontSigner

key_id = 'APKA...'  # CloudFront key pair ID
private_key = '''-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----'''

def generate_signed_url(url, expiry_hours=1):
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours)
    signer = CloudFrontSigner(key_id, lambda message: private_key.sign(message, 'SHA-1'))
    signed_url = signer.generate_presigned_url(
        url,
        date_less_than=expires
    )
    return signed_url
'''

S3_EVENT_NOTIFICATIONS = '''
# S3 → Lambda / SQS / SNS on object events

# 1. Create Lambda function (or SQS queue, SNS topic)
# 2. Configure S3 Event Notification:
#    Events: s3:ObjectCreated:* (Put, Post, Copy, Complete Multipart)
#            s3:ObjectRemoved:* (Delete)
#    Prefix filter: e.g., "uploads/" to only process uploads
#    Suffix filter: ".jpg" for images only
#    Destination: Lambda ARN

# Example Lambda (Python) triggered by S3 upload
import json
import boto3

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        # Generate thumbnail
        thumbnail_key = f"thumbnails/{key.split('/')[-1]}"
        # ... image processing code ...

        # Generate presigned URL for downstream service
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=3600
        )

        # Send to downstream queue
        # sqs.send_message(QueueUrl=..., MessageBody=json.dumps({...}))

    return {"status": "complete"}

# Use cases:
# - Virus scanning (ClamAV)
# - Image resizing (Sharp, Pillow)
# - Video transcoding (FFmpeg)
# - Metadata extraction (ExifTool)
# - Search indexing (Elasticsearch)
'''

S3_MULTIPART_UPLOADS = '''
# For files > 100MB (required) or to improve reliability

# 1. Initiate multipart upload
response = s3.create_multipart_upload(
    Bucket=BUCKET,
    Key=key,
    ContentType=content_type
)
upload_id = response['UploadId']

# 2. Upload parts (each part 5-10MB, except last)
part_numbers = []
for i, chunk in enumerate(read_chunks(file, chunk_size=10*1024*1024), start=1):
    part = s3.upload_part(
        Bucket=BUCKET,
        Key=key,
        PartNumber=i,
        UploadId=upload_id,
        Body=chunk
    )
    part_numbers.append({'PartNumber': i, 'ETag': part['ETag']})

# 3. Complete upload
s3.complete_multipart_upload(
    Bucket=BUCKET,
    Key=key,
    UploadId=upload_id,
    MultipartUpload={'Parts': part_numbers}
)

# If failed: abort to clean up
# s3.abort_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload_id)
'''

S3_COST_OPTIMIZATION = {
    "storage_classes": {
        "STANDARD": "Frequently accessed, lowest latency (99.9% availability)",
        "STANDARD_IA": "Infrequent access, 30-day minimum (min duration charge)",
        "ONEZONE_IA": "Same as IA but single AZ (cheaper, less durable)",
        "GLACIER_IR": "Glacier Instant Retrieval (within ms), 90-day minimum",
        "GLACIER": "Deep archive, 3-5h retrieval (7-180 day minimum)",
        "DEEP_ARCHIVE": "Cheapest, 12-48h retrieval (180 day minimum)",
    },
    "cost_calculator": """
Small files (<10KB): STANDARD (no cheaper alternative)
Medium (100MB): STANDARD → IA after 30 days → Glacier after 90
Large backups (GB+): GLACIER or DEEP_ARCHIVE immediately
Critical data: STANDARD or ONEZONE_IA (availability matters)
""",
    "transfer_costs": [
        "Upload to S3: FREE",
        "Download from S3: $0.09/GB (first 10TB)",
        "Cross-region transfer: Additional (CDN + Origin Fetch)",
        "Use CloudFront: cache hits → reduced S3 egress charges",
    ],
}

S3_INTEGRATION_WITH_BACKEND = '''
# models/file.py
class File(Base):
    __tablename__ = 'files'

    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(UUID, ForeignKey('users.id'), nullable=False)
    s3_key = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# After S3 upload completes, client calls:
POST /api/files
{
  "s3_key": "uploads/user-123/abc-image.jpg",
  "filename": "profile.jpg",
  "content_type": "image/jpeg",
  "size": 204800
}
→ Backend creates File record with user_id from auth token

# List user files:
GET /api/files → Files.where(user_id=current_user_id)
'''

S3_ERROR_HANDLING = '''
from botocore.exceptions import ClientError

try:
    s3.head_object(Bucket=BUCKET, Key=key)
except ClientError as e:
    error_code = e.response['Error']['Code']
    if error_code == 'NoSuchKey':
        raise FileNotFoundError()
    elif error_code == 'AccessDenied':
        raise PermissionError("No access to this file")
    elif error_code == 'InvalidRequest':
        raise ValueError("Invalid request")
    else:
        raise  # Re-raise unknown errors
'''

S3_COMPLIANCE_MODE = {
    "soc2": {
        "encryption": "SSE-KMS with customer-managed CMK (not AWS-managed)",
        "logging": "S3 access logs to separate bucket, immutable for 7 years",
        "versioning": "Enabled (retain all versions, cannot delete)",
        "access_control": "IAM policies + bucket policies + S3 Access Points",
        "monitoring": "S3 CloudWatch metrics + EventBridge alerts on public access",
    },
    "hipaa": {
        "phi_storage": "Encrypt at rest (SSE-KMS) + in transit (TLS)",
        "access_logs": "All accesses logged (who accessed what when)",
        "retention": "Retention policy to prevent deletion for 6 years",
        "backup": "Cross-region replication (CRR) for DR (every 4 hours RPO)",
    },
    "gdpr": {
        "data_residency": "S3 bucket in EU region for EU citizen data",
        "deletion": "S3 delete markers + versioning (definitive deletion possible)",
        "encryption": "AES-256 (SSE-S3) minimum, KMS for high sensitivity",
    },
}
