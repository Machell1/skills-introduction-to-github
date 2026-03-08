"""S3-compatible storage client using boto3.

Works with MinIO locally and AWS S3 or any S3-compatible service in production.
Configure via environment variables:
  - S3_ENDPOINT_URL: MinIO endpoint (e.g., http://minio:9000)
  - S3_ACCESS_KEY: Access key
  - S3_SECRET_KEY: Secret key
  - S3_BUCKET: Bucket name (default: jobsy)
  - S3_REGION: Region (default: us-east-1)
  - S3_PUBLIC_URL: Public-facing URL for generating file URLs
"""

import io
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from PIL import Image

logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "jobsy")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL", f"{S3_ENDPOINT_URL}/{S3_BUCKET}")

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOC_TYPES = {"application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
THUMBNAIL_SIZE = (300, 300)


def _get_client():
    """Create an S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket():
    """Create the bucket if it doesn't exist."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=S3_BUCKET)
    except Exception:
        client.create_bucket(Bucket=S3_BUCKET)
        logger.info("Created bucket: %s", S3_BUCKET)


def upload_file(
    file_data: bytes,
    content_type: str,
    folder: str,
    filename: str | None = None,
) -> dict:
    """Upload a file to S3 and return its URL.

    Args:
        file_data: Raw file bytes
        content_type: MIME type
        folder: Target folder (avatars, listings, chat)
        filename: Optional custom filename (auto-generated if None)

    Returns:
        dict with 'key', 'url', 'size', 'content_type'
    """
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB")

    if not filename:
        ext = _get_extension(content_type)
        filename = f"{uuid.uuid4().hex}{ext}"

    key = f"{folder}/{filename}"
    client = _get_client()

    client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=file_data,
        ContentType=content_type,
    )

    url = f"{S3_PUBLIC_URL}/{key}"
    logger.info("Uploaded %s (%d bytes)", key, len(file_data))

    return {
        "key": key,
        "url": url,
        "size": len(file_data),
        "content_type": content_type,
    }


def create_thumbnail(image_data: bytes, content_type: str) -> bytes:
    """Create a thumbnail from an image."""
    img = Image.open(io.BytesIO(image_data))
    img.thumbnail(THUMBNAIL_SIZE)

    output = io.BytesIO()
    fmt = "JPEG" if content_type == "image/jpeg" else "PNG"
    img.save(output, format=fmt)
    return output.getvalue()


def generate_presigned_url(folder: str, content_type: str, expiry_seconds: int = 3600) -> dict:
    """Generate a presigned URL for direct client upload."""
    ext = _get_extension(content_type)
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    client = _get_client()

    presigned_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expiry_seconds,
    )

    return {
        "upload_url": presigned_url,
        "key": key,
        "file_url": f"{S3_PUBLIC_URL}/{key}",
        "expires_in": expiry_seconds,
    }


def delete_file(key: str) -> bool:
    """Delete a file from S3."""
    client = _get_client()
    try:
        client.delete_object(Bucket=S3_BUCKET, Key=key)
        logger.info("Deleted %s", key)
        return True
    except Exception:
        logger.exception("Failed to delete %s", key)
        return False


def _get_extension(content_type: str) -> str:
    """Map MIME type to file extension."""
    extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    return extensions.get(content_type, ".bin")
