# Serverless Job Processing Platform

An event-driven platform on AWS for asynchronous task and image processing. Requests route through API Gateway into a producer Lambda, persist state in DynamoDB, buffer through SQS to decouple compute from burst traffic, and execute in a containerized Lambda worker that writes finished assets to S3. All infrastructure and code deploy automatically via GitHub Actions and Terraform using AWS OIDC.

**Live Frontend:** [https://srihasinaganti.github.io/job-platform/](https://srihasinaganti.github.io/job-platform/)

---

## Architecture

* **Frontend:** Single-page dashboard hosted on GitHub Pages.
* **API Gateway:** HTTP API routing requests for presigned upload URLs and job submissions.
* **Producer Lambda:** Generates S3 presigned URLs, initialises job records in DynamoDB, and enqueues tasks into SQS.
* **Queue (SQS):** Buffers incoming tasks, absorbs traffic spikes, and redrives unacknowledged messages on worker failure.
* **Worker Lambda:** Containerized runner (Docker in ECR) utilizing an atomic lease-fencing token protocol to prevent split-brain writes and duplicate processing.
* **Data Layer (DynamoDB):** Tracks state transitions (`PENDING` -> `PROCESSING` -> `COMPLETED`) using conditional writes for distributed locking.
* **Storage (S3):** Stores raw uploads, processed outputs, and remote Terraform state. Automatically garbage-collects orphaned artifacts from stale worker commits.
* **CI/CD:** GitHub Actions with AWS OIDC running automated linting, Docker builds, ECR container pushes, and Terraform deployments.

---

## Distributed Coordination & Fencing Protocol

To prevent split-brain execution and stale writes when an SQS visibility timeout lapses during a slow execution:

1. **Atomic Lease Claim:** Workers conditionally claim jobs (`status IN (PENDING, FAILED) OR processing_started_at < lease_cutoff`) and assign a unique, monotonic `lease_token`.
2. **Fenced Completion:** Results commit to DynamoDB only if `lease_token = :my_token`. If another worker reclaimed the job, the stale worker's commit fails with a `ConditionalCheckFailedException`.
3. **Artifact Cleanup:** Fenced-out workers intercept write rejections and automatically delete orphaned S3 result files to prevent dangling storage bloat.

---

## Performance & Chaos Verification Results

Empirically validated under 100-job burst concurrency with 25% unhandled container termination (`SIGKILL` via `os._exit(137)`):

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Dispatched Jobs** | 100 / 100 Accepted | 100% accepted via API Gateway (zero dropped or 503 errors under paced ingress) |
| **Terminal Success Rate** | 100.00% (100/100) | 75 nominal path (Attempt 1) + 25 crash-recovered (Attempt 2) |
| **Terminal Failures** | 0 | Zero dropped jobs, deadlocks, or unhandled message loss |
| **Nominal Latency (p50 / p90)** | 2.0s / 5.0s | End-to-end ingest, queue dispatch, and LANCZOS image transformation |
| **Recovery Latency (p50 / p99)** | 18.0s / 21.0s | SQS visibility timeout (15s) + lease expiration (10s) test profile (scales to 180s/120s in prod) |
| **Split-Brain Prevention** | 100% Rejected & Cleaned | Verified via simulated zombie worker stall (>15s); stale writes rejected and S3 artifacts purged |
| **CI/CD Pipeline Run** | ~3m 30s | Automated test suite, container build, immutable ECR push, and Terraform apply |

---

## Tech Stack

* **Cloud:** AWS (Lambda, API Gateway, DynamoDB, SQS, S3, ECR, IAM OIDC)
* **Infrastructure as Code:** Terraform (S3 Remote Backend + State Locking)
* **DevOps & Containers:** Docker, GitHub Actions, GitHub Pages
* **Languages & Runtimes:** Python 3.12, JavaScript (ES6+), Pillow
