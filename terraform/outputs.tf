output "api_endpoint" {
  description = "HTTP API Gateway base URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "worker_function_arn" {
  description = "ARN of the worker Lambda function"
  value       = aws_lambda_function.worker.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for the worker image"
  value       = aws_ecr_repository.worker.repository_url
}