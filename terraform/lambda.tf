resource "aws_lambda_function" "submit" {
  function_name    = "job-submit"
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = "../build/submit.zip"
  source_code_hash = filebase64sha256("../build/submit.zip")
  role             = aws_iam_role.submit_role.arn
  timeout          = 10

  environment {
    variables = {
      JOBS_TABLE = aws_dynamodb_table.jobs.name
      RAW_BUCKET = aws_s3_bucket.raw_uploads.bucket
      QUEUE_URL  = aws_sqs_queue.job_queue.id
    }
  }
}

resource "aws_lambda_function" "reconcile" {
  function_name    = "job-reconcile"
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = "../build/reconcile.zip"
  source_code_hash = filebase64sha256("../build/reconcile.zip")
  role             = aws_iam_role.reconcile_role.arn
  timeout          = 30

  environment {
    variables = {
      JOBS_TABLE = aws_dynamodb_table.jobs.name
      QUEUE_URL  = aws_sqs_queue.job_queue.id
    }
  }
}

resource "aws_cloudwatch_event_rule" "reconcile_schedule" {
  name                = "job-reconcile-schedule"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "reconcile_target" {
  rule = aws_cloudwatch_event_rule.reconcile_schedule.name
  arn  = aws_lambda_function.reconcile.arn
}

resource "aws_lambda_permission" "allow_eventbridge_reconcile" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reconcile.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reconcile_schedule.arn
}

resource "aws_lambda_function" "worker" {
  function_name = "job-worker"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
  role          = aws_iam_role.worker_role.arn
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      JOBS_TABLE     = aws_dynamodb_table.jobs.name
      RAW_BUCKET     = aws_s3_bucket.raw_uploads.bucket
      RESULTS_BUCKET = aws_s3_bucket.results.bucket
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_to_worker" {
  event_source_arn = aws_sqs_queue.job_queue.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1

  scaling_config {
    maximum_concurrency = 10
  }
}

resource "aws_lambda_function" "status" {
  function_name    = "job-status"
  filename         = "../build/status.zip"
  source_code_hash = filebase64sha256("../build/status.zip")
  handler          = "handler.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.status_role.arn

  environment {
    variables = {
      JOBS_TABLE     = aws_dynamodb_table.jobs.name
      RESULTS_BUCKET = aws_s3_bucket.results.bucket
    }
  }
}