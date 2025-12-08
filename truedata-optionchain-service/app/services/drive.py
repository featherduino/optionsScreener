"""S3 uploader used by the chart endpoints when `upload=drive` is requested."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_s3_client = None


class DriveConfigurationError(RuntimeError):
    """Raised when the S3 upload integration is not configured properly."""


class DriveUploadError(RuntimeError):
    """Raised when uploading to S3 fails."""


def _get_s3_client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL")

    if not access_key or not secret_key:
        raise DriveConfigurationError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required")

    try:
        session = boto3.session.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        _s3_client = session.client("s3", endpoint_url=endpoint_url)
        return _s3_client
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - boto client errors
        raise DriveConfigurationError(f"Failed to initialize S3 client: {exc}") from exc


def _build_key(filename: str) -> str:
    prefix = os.getenv("S3_BUCKET_PREFIX", "charts")
    prefix = prefix.strip("/")
    if prefix:
        return f"{prefix}/{filename}"
    return filename


def _public_url(bucket: str, key: str) -> str:
    base = os.getenv("S3_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{key}"
    region = os.getenv("AWS_REGION", "us-east-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def upload_png(filename: str, payload: bytes) -> dict[str, Any]:
    """Upload PNG bytes to the configured S3 bucket."""
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise DriveConfigurationError("S3_BUCKET_NAME is required for uploads")

    key = _build_key(filename)
    client = _get_s3_client()
    extra = {"ContentType": "image/png"}
    acl = os.getenv("S3_OBJECT_ACL", "public-read")
    if acl:
        extra["ACL"] = acl

    try:
        client.put_object(Bucket=bucket, Key=key, Body=payload, **extra)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS failures
        raise DriveUploadError(f"S3 upload failed: {exc}") from exc

    url = _public_url(bucket, key)
    return {
        "bucket": bucket,
        "key": key,
        "url": url,
    }
