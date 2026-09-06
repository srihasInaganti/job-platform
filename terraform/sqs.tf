resource "aws_sqs_queue" "job_queue" {
  name                       = "job-queue"
  visibility_timeout_seconds = 180
}

resource "aws_sqs_queue" "job_dlq" {
  name                      = "job-dlq"
}

resource "aws_sqs_queue_redrive_policy" "job_queue_redrive" {
  queue_url = aws_sqs_queue.job_queue.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.job_dlq.arn
    maxReceiveCount     = 3
  })
}