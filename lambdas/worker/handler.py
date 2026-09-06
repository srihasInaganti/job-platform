import io
import json
import os
import time
import boto3
from botocore.exceptions import ClientError
from PIL import Image
from typing import Any, cast

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RAW_BUCKET = os.environ["RAW_BUCKET"]
RESULTS_BUCKET = os.environ["RESULTS_BUCKET"]
LEASE_SECONDS = 120  # a PROCESSING job older than this is considered abandoned


def handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        process_one_job(body["job_id"], context)


def try_claim(job_id, context):
    now = int(time.time())
    lease_cutoff = now - LEASE_SECONDS
    try:
        # ExpressionAttributeNames used defensively: "status" (and several close
        # variants) are reserved words in DynamoDB's expression syntax. `job_status`
        # is safe as written, but if you ever rename this field to `status`, an
        # unaliased ConditionExpression/UpdateExpression referencing it will fail
        # with a cryptic "reserved keyword" error. Aliasing it now means a future
        # rename is a one-line change instead of a debugging session.
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
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            return False  # someone else holds a live lease — treat as success, let SQS delete the msg
        raise

def process_one_job(job_id: str, context: Any):
    response = table.get_item(Key={"job_id": job_id})
    raw_item = response.get("Item")
    if not raw_item:
        return

    # Cast to standard dict so .get() and key lookups have normal dictionary semantics
    job = cast(dict[str, Any], raw_item)

    if not try_claim(job_id, context):
        return

    try:
        s3_key = str(job["s3_key"])
        obj = s3.get_object(Bucket=RAW_BUCKET, Key=s3_key)
        img = Image.open(io.BytesIO(obj["Body"].read()))

        op = str(job.get("operation", ""))
        params: dict[str, Any] = job.get("params") or {}
        fmt = str(params.get("format", img.format or "PNG"))

        if op == "resize":
            width = int(params.get("width", 200))
            ratio = width / img.width
            img = img.resize((width, int(img.height * ratio)))
        elif op == "thumbnail":
            img.thumbnail((150, 150))
        # "convert" needs no pixel changes — just saves in a different format below

        buf = io.BytesIO()
        img.save(buf, format=fmt)
        buf.seek(0)

        result_key = f"{job_id}.{fmt.lower()}"  # deterministic key — safe to overwrite on retry
        s3.put_object(Bucket=RESULTS_BUCKET, Key=result_key, Body=buf)

        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :done, result_key = :rk",
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={":done": "COMPLETED", ":rk": result_key},
        )
    except Exception:
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :failed",
            ExpressionAttributeNames={"#s": "job_status"},
            ExpressionAttributeValues={":failed": "FAILED"},
        )
        raise  # re-raise so SQS still counts this as a failed delivery for DLQ/retry purposes