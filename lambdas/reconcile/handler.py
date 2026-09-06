import os, json, time, boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
QUEUE_URL = os.environ["QUEUE_URL"]
STALE_SECONDS = 300  # 5 minutes — a healthy job should have moved off PENDING well before this

def handler(event, context):
    cutoff = int(time.time()) - STALE_SECONDS
    resp = table.scan(FilterExpression=Attr("job_status").eq("PENDING") & Attr("created_at").lt(cutoff))
    for job in resp.get("Items", []):
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"job_id": job["job_id"]}))