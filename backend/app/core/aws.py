"""boto3 S3 + SQS clients (CLAUDE.md §3).

``AWS_ENDPOINT_URL`` set → LocalStack (local dev); unset → real AWS (ECS IAM
role). Clients are lazy module singletons — boto3 clients are thread-safe and
fine to share.
"""

from __future__ import annotations

import functools

import boto3
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


def _client(service: str):
    kwargs: dict = {"region_name": settings.AWS_REGION}
    if settings.AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
    if settings.AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client(service, **kwargs)


@functools.cache
def s3():
    return _client("s3")


@functools.cache
def sqs():
    return _client("sqs")


def ensure_infra() -> None:
    """Best-effort create the bucket + queue — for LocalStack. On real AWS
    (``AWS_ENDPOINT_URL`` unset) this is a no-op: infra is provisioned by IaC."""
    if not settings.AWS_ENDPOINT_URL:
        return
    try:
        kw: dict = {"Bucket": settings.S3_BUCKET_NAME}
        if settings.AWS_REGION != "us-east-1":  # S3 requires this outside us-east-1
            kw["CreateBucketConfiguration"] = {"LocationConstraint": settings.AWS_REGION}
        s3().create_bucket(**kw)
    except Exception as exc:  # noqa: BLE001 — already-exists etc.
        logger.debug("s3_ensure_bucket", note=str(exc))
    try:
        name = (settings.SQS_QUEUE_URL or "").rstrip("/").rsplit("/", 1)[-1] or "genie-jobs"
        sqs().create_queue(QueueName=name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("sqs_ensure_queue", note=str(exc))
    logger.info("aws_infra_ready", bucket=settings.S3_BUCKET_NAME, queue=settings.SQS_QUEUE_URL)
