# Serverless Job Processing Platform

An event-driven platform on AWS for asynchronous task and image processing. Users upload files and dispatch jobs through a static web dashboard. Requests route through API Gateway into a producer Lambda, persist state in DynamoDB, buffer through SQS to smooth out burst traffic, and execute in a containerized Lambda worker that writes finished assets to S3. All infrastructure and code deploy automatically via GitHub Actions and Terraform using OIDC.

**Live Frontend:** [https://srihasinaganti.github.io/job-platform/](https://srihasinaganti.github.io/job-platform/)

---

## Architecture

* **Frontend:** Single-page dashboard hosted on GitHub Pages.
* **API Gateway:** HTTP API routing requests for presigned upload URLs and job dispatches.
* **Producer Lambda:** Generates S3 presigned URLs, initialises job records in DynamoDB, and enqueues tasks.
* **Data Layer (DynamoDB):** Tracks state transitions (`PENDING` -> `PROCESSING` -> `COMPLETED`) and execution metadata.
* **Queue (SQS):** Buffers tasks to decouple ingestion from compute and absorb burst traffic.
* **Worker Lambda:** Containerized task runner packaged via Docker in ECR that pulls from SQS, executes compute, and updates DynamoDB.
* **Storage (S3):** Stores raw uploads, processed outputs, and remote Terraform state.
* **CI/CD:** GitHub Actions with AWS OIDC (no static secrets) running automated tests, Docker builds, and Terraform applies.

---

## Performance & Load Test Results

Benchmarked with concurrent traffic across the live API Gateway and Lambda ingestion layer:

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Median Latency (p50)** | **20 ms** | API Gateway + Lambda execution round-trip |
| **p99 Latency** | **110 ms** | High-percentile latency under concurrent load |
| **Cold Start vs. Warm** | **874 ms vs. 20 ms** | Initial container start vs. warm instance reuse |
| **Sustained Throughput** | **~350 req/sec** | Measured across concurrent warm instances |
| **Traffic Shaping** | **HTTP 429 Protection** | Built-in rate limiting prevented backend exhaustion under burst load |
| **CI/CD Pipeline Run** | **~3m 30s** | Full test, Docker build, ECR push, and Terraform apply |

---

## Tech Stack

* **Cloud:** AWS (Lambda, API Gateway, DynamoDB, SQS, S3, ECR, IAM OIDC)
* **Infrastructure as Code:** Terraform (S3 Remote Backend)
* **DevOps & Containers:** Docker, GitHub Actions, GitHub Pages
* **Languages:** Python 3.12, JavaScript
