# Serverless Job Processing Platform

An event-driven platform on AWS designed for asynchronous task processing. It uses an interactive web dashboard to submit workloads through an HTTP API, buffers tasks in SQS, and processes them with a containerized Lambda worker that writes results to S3. All infrastructure and code deploy automatically via GitHub Actions and Terraform using OIDC.

**Live Frontend:** [https://srihasinaganti.github.io/job-platform/](https://srihasinaganti.github.io/job-platform/)

---

## Architecture

* **Frontend:** Single-page dashboard hosted on GitHub Pages.
* **API:** Amazon API Gateway (HTTP API) triggers a lightweight producer Lambda.
* **Queue:** Amazon SQS buffers tasks to decouple ingestion from compute.
* **Worker:** Containerized AWS Lambda packaged via Docker and stored in Amazon ECR.
* **Storage:** Amazon S3 stores task artifacts, outputs, and remote Terraform state.
* **CI/CD:** GitHub Actions with AWS OIDC (no stored secrets) running automated tests, Docker builds, and Terraform applies.

---

## Performance & Metrics

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **API Ingestion Latency** | ~45ms - 75ms | Time to accept payload and push to SQS |
| **Worker Processing Time** | ~1.2s - 2.8s | Container execution duration per task |
| **Queue Batch Size** | 10 messages | Max batch read per worker invocation (limited by AWS free tier) |
| **Worker Memory Allocation** | 1024 MB | Tuned for compute/cost balance |
| **Deployment Time** | ~3m 30s | Full CI test, Docker build, and Terraform apply |

---

## Tech Stack

* **Cloud & Serverless:** AWS (Lambda, API Gateway, SQS, S3, ECR, CloudWatch, IAM OIDC)
* **Infrastructure as Code:** Terraform
* **DevOps & Containers:** Docker, GitHub Actions, GitHub Pages
* **Languages & Testing:** Python 3.14, Pytest, JavaScript
