terraform {
  backend "s3" {
    bucket  = "job-platform-tfstate-426592733563"
    key     = "production/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}