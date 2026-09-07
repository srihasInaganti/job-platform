import io
import json
import logging
import os
import time
import uuid
from typing import Any, Optional, cast

import boto3
from botocore.exceptions import ClientError
from PIL import Image

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RAW_BUCKET = os.environ["RAW_BUCKET"]
RESULTS_BUCKET = os.environ["RESULTS_BUCKET"]

# Set LEASE_SECONDS conservatively below SQS Visibility Timeout (e.g. 10s vs 15s)
LEASE_SECONDS = int(os.environ.get("LEASE_SECONDS", "10"))

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log(event_type: str, **kwargs: Any) -> None:
    logger.info(json.dumps({"event": event_type, **kwargs}))


def handler(event: dict[str, Any], context: Any) -> None:
    for record in event["Records"]:
        body = json.loads(record["body"])
        process_one_job(body["job_id"], context)

def try_claim(job_id: str, lease_token: str, context: Any) -> Optional[int]:
    """
    Atomically claims or reclaims a job.
    Returns the updated attempt_count on success, or None if the lease is still active.
    """
    now = int(time.time())
    lease_cutoff = now - LEASE_SECONDS
    worker_id = context.aws_request_id if context else str(uuid.uuid4())

    try:
        res = table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #s = :processing, "
                "worker_id = :wid, "
                "lease_token = :token, "
                "processing_started_at = :now, "
                "attempt_count = if_not_exists(attempt_count, :zero) + :one"
            ),
            ConditionExpression=(
                "#s = :pending OR #s = :failed "
                "OR (#s = :processing_state AND processing_started_at < :lease_cutoff)"
            ),
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={
                ":processing": "PROCESSING",
                ":pending": "PENDING",
                ":failed": "FAILED",
                ":processing_state": "PROCESSING",
                ":lease_cutoff": lease_cutoff,
                ":wid": worker_id,
                ":token": lease_token,
                ":now": now,
                ":zero": 0,
                ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )
        attributes = cast(dict[str, Any], res.get("Attributes") or {})
        current_attempts = int(cast(Any, attributes.get("attempt_count", 1)))
        log("job_claimed", job_id=job_id, worker_id=worker_id, lease_token=lease_token, attempt=current_attempts)
        return current_attempts
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            log("job_claim_skipped", job_id=job_id, reason="held_by_another_worker_or_terminal")
            return None
        raise

def complete_job_fenced(job_id: str, lease_token: str, result_key: str) -> bool:
    """
    Fenced write: only succeeds if our lease_token is still active in DynamoDB.
    If another worker reclaimed this job while we stalled, this write fails and cleans up S3.
    """
    now = int(time.time())
    try:
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :done, result_key = :rk, completed_at = :now",
            ConditionExpression="lease_token = :my_token",
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={
                ":done": "COMPLETED",
                ":rk": result_key,
                ":my_token": lease_token,
                ":now": now,
            },
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            log("fenced_out_on_complete", job_id=job_id, lease_token=lease_token)
            # Purge orphaned S3 object to prevent dangling, untracked artifacts
            try:
                s3.delete_object(Bucket=RESULTS_BUCKET, Key=result_key)
                log("cleaned_orphaned_s3", job_id=job_id, result_key=result_key)
            except Exception as del_err:
                log("cleanup_orphaned_s3_failed", job_id=job_id, error=str(del_err))
            return False
        raise


def process_one_job(job_id: str, context: Any) -> None:
    response = table.get_item(Key={"job_id": job_id})
    raw_item = response.get("Item")
    if not raw_item:
        return

    job = cast(dict[str, Any], raw_item)

    # Generate a unique fencing token for this claim attempt
    lease_token = str(uuid.uuid4())

    attempts = try_claim(job_id, lease_token, context)
    if attempts is None:
        # Fail the Lambda execution so SQS re-queues after visibility timeout
        raise RuntimeError(f"Job {job_id} currently locked by another worker lease")

    params: dict[str, Any] = job.get("params") or {}
    start_time = time.time()

    try:
        s3_key = str(job["s3_key"])
        obj = s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)
        img = Image.open(io.BytesIO(obj["Body"].read()))

        op = str(job.get("operation", ""))
        fmt = str(params.get("format", img.format or "PNG")).upper()
        if fmt == "JPG":
            fmt = "JPEG"

        # Supported Operations
        if op == "resize":
            width = int(params.get("width", 200))
            ratio = width / img.width
            img = img.resize((width, int(img.height * ratio)), Image.Resampling.LANCZOS)
        elif op == "thumbnail":
            size = int(params.get("size", 150))
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
        elif op == "grayscale":
            img = img.convert("L")

        # Protect against JPEG RGBA saves
        if fmt == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format=fmt)
        buf.seek(0)

        ext = "jpg" if fmt == "JPEG" else fmt.lower()
        result_key = f"{job_id}.{ext}"
        s3.put_object(
            Bucket=RESULTS_BUCKET,
            Key=result_key,
            Body=buf,
            ContentType=f"image/{ext}",
        )
        
        # Check if chaos delay is requested
        sleep_delay = int(params.get("chaos_delay_sec", 0))
        if sleep_delay > 0 and attempts == 1:
            log("zombie_worker_sleeping", job_id=job_id, delay=sleep_delay, lease_token=lease_token)
            time.sleep(sleep_delay)


        if complete_job_fenced(job_id, lease_token, result_key):
            duration_ms = int((time.time() - start_time) * 1000)
            log("job_completed", job_id=job_id, duration_ms=duration_ms, operation=op)

    except Exception as e:
        log("job_failed", job_id=job_id, error=str(e))
        try:
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #s = :failed",
                ConditionExpression="lease_token = :my_token",
                ExpressionAttributeNames={"#s": "job_status"},
                ExpressionAttributeValues={":failed": "FAILED", ":my_token": lease_token},
            )
        except ClientError:
            pass  # If another worker reclaimed it already, do not overwrite with FAILED
        raise