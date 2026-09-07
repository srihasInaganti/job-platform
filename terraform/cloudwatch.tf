# 1. Queue Depth Alarm
resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "job-queue-depth-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 100
  dimensions = {
    QueueName = aws_sqs_queue.job_queue.name
  }
}

# 2. Oldest Message Age (Latency/Wait SLA)
resource "aws_cloudwatch_metric_alarm" "queue_oldest_message" {
  alarm_name          = "job-queue-oldest-message-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 300 # 5 minutes
  dimensions = {
    QueueName = aws_sqs_queue.job_queue.name
  }
}

# 3. Worker Lambda Error Rate
resource "aws_cloudwatch_metric_alarm" "worker_errors" {
  alarm_name          = "job-worker-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  dimensions = {
    FunctionName = aws_lambda_function.worker.function_name
  }
}

# 4. Worker Lambda Throttles
resource "aws_cloudwatch_metric_alarm" "worker_throttles" {
  alarm_name          = "job-worker-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  dimensions = {
    FunctionName = aws_lambda_function.worker.function_name
  }
}

# 5. DLQ Size (Immediate triage alert)
resource "aws_cloudwatch_metric_alarm" "dlq_size" {
  alarm_name          = "job-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 0
  dimensions = {
    QueueName = aws_sqs_queue.job_dlq.name
  }
}