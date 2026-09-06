import json, os, uuid, time, boto3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sqs = boto3.client("sqs")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RAW_BUCKET = os.environ["RAW_BUCKET"]
QUEUE_URL = os.environ["QUEUE_URL"]

def handler(event, context):
    route = event["routeKey"]
    body = json.loads(event.get("body") or "{}")

    if route == "POST /uploads":
        return create_presigned_upload(body)
    if route == "POST /jobs":
        return create_job(body)
    return {"statusCode": 404, "body": json.dumps({"error": "unknown route"})}

def create_presigned_upload(body):
    upload_id = str(uuid.uuid4())
    content_type = body.get("content_type", "image/jpeg")
    s3_key = f"uploads/{upload_id}"

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": RAW_BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=300,  # 5 minutes to complete the upload
    )
    return {"statusCode": 200, "body": json.dumps({"upload_url": url, "s3_key": s3_key})}

def create_job(body):
    s3_key = body.get("s3_key")
    operation = body.get("operation")

    if not s3_key or operation not in ("resize", "thumbnail", "convert"):
        return {"statusCode": 400, "body": json.dumps({"error": "invalid request"})}

    job_id = str(uuid.uuid4())

    # NOTE on the dual-write gap: if put_item succeeds but send_message fails
    # (network blip, throttling, Lambda timeout between the two calls), the
    # job is stuck PENDING with no queued message. This is a known, documented
    # tradeoff — see Step 3's reconciliation sweep, which is the mitigation
    # chosen instead of a full transactional outbox pattern.
    table.put_item(Item={
        "job_id": job_id,
        "s3_key": s3_key,
        "operation": operation,
        "params": body.get("params", {}),
        "job_status": "PENDING",
        "created_at": int(time.time()),
    })

    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"job_id": job_id}))

    return {"statusCode": 202, "body": json.dumps({"job_id": job_id, "status": "PENDING"})}