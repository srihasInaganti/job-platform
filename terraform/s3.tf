data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "raw_uploads" {
  bucket = "job-platform-raw-uploads-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "results" {
  bucket = "job-platform-results-${data.aws_caller_identity.current.account_id}"
}

# Block public access on both buckets — access is via presigned URLs / IAM only.
resource "aws_s3_bucket_public_access_block" "raw_uploads_block" {
  bucket                  = aws_s3_bucket.raw_uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "results_block" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_uploads_sse" {
  bucket = aws_s3_bucket.raw_uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "raw_uploads_cors" {
  bucket = aws_s3_bucket.raw_uploads.id
  cors_rule {
    allowed_methods = ["PUT", "GET"]
    allowed_origins = ["*"]   # tighten to your frontend origin later
    allowed_headers = ["*"]
  }
}