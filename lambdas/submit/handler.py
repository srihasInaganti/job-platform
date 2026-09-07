import json, os, uuid, time, boto3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sqs = boto3.client("sqs")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RAW_BUCKET = os.environ["RAW_BUCKET"]
QUEUE_URL = os.environ["QUEUE_URL"]

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}

def handler(event, context):
    route = event.get("routeKey") or f"{event.get('httpMethod', '')} {event.get('resource', '')}".strip()
    body = json.loads(event.get("body") or "{}")

    if route in ("POST /uploads", "POST /upload"):
        return create_presigned_upload(body)
    if route in ("POST /jobs", "POST /job"):
        return create_job(body)
    return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": "unknown route"})}

def create_presigned_upload(body):
    upload_id = str(uuid.uuid4())
    content_type = body.get("content_type", "image/jpeg")
    s3_key = f"uploads/{upload_id}"

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": RAW_BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=300,
    )
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"upload_url": url, "s3_key": s3_key}),
    }

def create_job(body):
    s3_key = body.get("s3_key")
    operation = body.get("operation")

    # Added "grayscale" to allowed operations
    if not s3_key or operation not in ("resize", "thumbnail", "convert", "grayscale"):
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"error": "invalid request"})}

    job_id = str(uuid.uuid4())

    table.put_item(Item={
        "job_id": job_id,
        "s3_key": s3_key,
        "operation": operation,
        "params": body.get("params", {}),
        "job_status": "PENDING",
        "created_at": int(time.time()),
    })

    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"job_id": job_id}))

    return {
        "statusCode": 202,
        "headers": CORS_HEADERS,
        "body": json.dumps({"job_id": job_id, "status": "PENDING"}),
    }