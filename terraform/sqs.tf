resource "aws_sqs_queue" "job_queue" {
  name                       = "job-queue"
  visibility_timeout_seconds = 180   # generous margin over the worker's 60s Lambda timeout
}