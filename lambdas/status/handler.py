import json, os, boto3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["JOBS_TABLE"])
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}

def handler(event, context):
    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")

    if not job_id:
        return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"error": "missing job_id"})}

    item = table.get_item(Key={"job_id": job_id}).get("Item")
    if not item:
        return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": "not found"})}

    response = {"job_id": job_id, "status": item["job_status"]}
    
    if item["job_status"] == "COMPLETED" and "result_key" in item:
        response["result_key"] = item["result_key"]
        if RESULTS_BUCKET:
            response["result_url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": RESULTS_BUCKET, "Key": item["result_key"]},
                ExpiresIn=3600,
            )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps(response),
    }