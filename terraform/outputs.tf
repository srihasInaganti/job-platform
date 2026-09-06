output "api_endpoint" {
  description = "HTTP API Gateway base URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}