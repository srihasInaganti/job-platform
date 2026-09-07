import io
import json
import os
import time
import boto3
from botocore.exceptions import ClientError
from PIL import Image
from typing import Any, cast
import logging

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RAW_BUCKET = os.environ["RAW_BUCKET"]
RESULTS_BUCKET = os.environ["RESULTS_BUCKET"]
LEASE_SECONDS = 120  # a PROCESSING job older than this is considered abandoned

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log(event_type, **kwargs):
    logger.info(json.dumps({"event": event_type, **kwargs}))


def handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        process_one_job(body["job_id"], context)


def try_claim(job_id, context):
    now = int(time.time())
    lease_cutoff = now - LEASE_SECONDS
    try:
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :processing, worker_id = :wid, processing_started_at = :now",
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
                ":wid": context.aws_request_id,
                ":now": now,
            },
        )
        log("job_claimed", job_id=job_id, worker_id=context.aws_request_id)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            log("job_claim_skipped", job_id=job_id, reason="held_by_another_worker")
            return False
        raise


def process_one_job(job_id: str, context: Any):
    response = table.get_item(Key={"job_id": job_id})
    raw_item = response.get("Item")
    if not raw_item:
        return

    job = cast(dict[str, Any], raw_item)

    if not try_claim(job_id, context):
        return

    start_time = time.time()

    try:
        s3_key = str(job["s3_key"])
        obj = s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)
        img = Image.open(io.BytesIO(obj["Body"].read()))

        op = str(job.get("operation", ""))
        params: dict[str, Any] = job.get("params") or {}
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
        # "convert" requires no pixel changes — simply re-encoded below

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
            ContentType=f"image/{ext}"
        )

        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :done, result_key = :rk",
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={":done": "COMPLETED", ":rk": result_key},
        )
        duration_ms = int((time.time() - start_time) * 1000)
        log("job_completed", job_id=job_id, duration_ms=duration_ms, operation=op)

    except Exception as e:
        log("job_failed", job_id=job_id, error=str(e))
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :failed",
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={":failed": "FAILED"},
        )
        raise