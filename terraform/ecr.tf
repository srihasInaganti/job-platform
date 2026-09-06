resource "aws_ecr_repository" "worker" {
  name                 = "job-worker"
  image_tag_mutability = "IMMUTABLE"
}