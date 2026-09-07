import io
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_BASE = "https://irvf3ci138.execute-api.us-east-1.amazonaws.com"
TOTAL_JOBS = 500
CONCURRENCY = 30
CHAOS_INJECTION_PCT = 20  # 20% of jobs will simulate hard SIGKILL failure on Attempt 1
POLL_INTERVAL_SEC = 1.5
MAX_TIMEOUT_SEC = 90.0

def create_http_session(pool_size: int) -> requests.Session:
    """Configures a connection-pooled requests session with retries for transient API GW drops."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.2,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def prepare_shared_fixture(session: requests.Session) -> str:
    """Creates and uploads a single representative image payload to reuse across benchmark calls."""
    print("Preparing shared baseline fixture in S3...")
    r_up = session.post(f"{API_BASE}/uploads", json={"content_type": "image/jpeg"}).json()
    upload_url = r_up["upload_url"]
    s3_key = r_up["s3_key"]

    buf = io.BytesIO()
    Image.new("RGB", (600, 600), color=(130, 80, 200)).save(buf, format="JPEG", quality=85)
    
    upload_resp = session.put(upload_url, data=buf.getvalue(), headers={"Content-Type": "image/jpeg"})
    if upload_resp.status_code not in (200, 204):
        raise RuntimeError(f"Failed to upload fixture payload: {upload_resp.status_code}")
    
    print(f"Fixture ready at key: {s3_key}")
    return s3_key

def calculate_percentile(sorted_data: List[float], percentile: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return round(d0 + d1, 3)

def execute_benchmark_worker(job_idx: int, s3_key: str, session: requests.Session) -> Dict[str, Any]:
    t0 = time.time()
    
    # 1. Dispatch job via API Gateway
    submit_payload = {
        "s3_key": s3_key,
        "operation": "grayscale",
        "params": {"chaos_kill_pct": CHAOS_INJECTION_PCT}
    }
    
    try:
        r_post = session.post(f"{API_BASE}/jobs", json=submit_payload, timeout=10)
        if r_post.status_code != 202:
            return {"index": job_idx, "status": "SUBMIT_FAILED", "elapsed": time.time() - t0, "attempts": 0}
        
        job_id = r_post.json()["job_id"]
    except Exception as exc:
        return {"index": job_idx, "status": "SUBMIT_EXCEPTION", "error": str(exc), "elapsed": time.time() - t0, "attempts": 0}

    # 2. Poll until terminal state
    while time.time() - t0 < MAX_TIMEOUT_SEC:
        try:
            res = session.get(f"{API_BASE}/jobs/{job_id}", timeout=5).json()
            status = res.get("status")
            attempts = res.get("attempt_count", 0)
            
            if status == "COMPLETED":
                total_duration = time.time() - t0
                crashed_and_recovered = total_duration > 10.0  # SQS 15s visibility delay window
                return {
                    "index": job_idx,
                    "job_id": job_id,
                    "status": "COMPLETED",
                    "elapsed": round(total_duration, 3),
                    "crashed_and_recovered": crashed_and_recovered,
                    "attempts": attempts
                }
            elif status == "FAILED":
                return {
                    "index": job_idx,
                    "job_id": job_id,
                    "status": "FAILED",
                    "elapsed": round(time.time() - t0, 3),
                    "attempts": attempts
                }
        except Exception:
            pass  # Absorb transient network hiccup during polling
            
        time.sleep(POLL_INTERVAL_SEC)
        
    return {
        "index": job_idx,
        "job_id": job_id,
        "status": "TIMEOUT",
        "elapsed": MAX_TIMEOUT_SEC,
        "attempts": 0
    }

def main():
    session = create_http_session(CONCURRENCY)
    shared_s3_key = prepare_shared_fixture(session)

    print(f"\n{'='*70}")
    print(f"Executing Load Benchmark: {TOTAL_JOBS} Jobs @ {CONCURRENCY} Max Workers")
    print(f"Chaos Rate: {CHAOS_INJECTION_PCT}% SIGKILL on Attempt 1")
    print(f"{'='*70}\n")

    results: List[Dict[str, Any]] = []
    start_bench_time = time.time()

    completed_so_far = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        future_map = {
            executor.submit(execute_benchmark_worker, i, shared_s3_key, session): i 
            for i in range(TOTAL_JOBS)
        }
        
        for future in as_completed(future_map):
            res = future.result()
            results.append(res)
            completed_so_far += 1
            if completed_so_far % 50 == 0 or completed_so_far == TOTAL_JOBS:
                print(f"Progress: [{completed_so_far}/{TOTAL_JOBS}] jobs resolved ({(completed_so_far/TOTAL_JOBS)*100:.0f}%)")

    total_wall_clock = time.time() - start_bench_time

    # Metric aggregation
    completed_jobs = [r for r in results if r["status"] == "COMPLETED"]
    direct_jobs = [r for r in completed_jobs if not r.get("crashed_and_recovered")]
    recovered_jobs = [r for r in completed_jobs if r.get("crashed_and_recovered")]
    failed_jobs = [r for r in results if r["status"] in ("FAILED", "SUBMIT_FAILED", "TIMEOUT")]

    all_latencies = sorted([r["elapsed"] for r in completed_jobs])
    nominal_latencies = sorted([r["elapsed"] for r in direct_jobs])
    recovery_latencies = sorted([r["elapsed"] for r in recovered_jobs])

    overall_throughput = round(len(completed_jobs) / total_wall_clock, 2)
    integrity_rate = (len(completed_jobs) / TOTAL_JOBS) * 100

    print("\n" + "="*70)
    print("                      SYSTEM BENCHMARK RESULTS                       ")
    print("="*70)
    print(f"Total Dispatched Jobs  : {TOTAL_JOBS}")
    print(f"Concurrency Level      : {CONCURRENCY} threads")
    print(f"Total Test Duration    : {total_wall_clock:.2f}s")
    print(f"Sustained Throughput   : {overall_throughput} jobs/sec")
    print(f"Data Integrity Rate    : {integrity_rate:.2f}% ({len(completed_jobs)}/{TOTAL_JOBS})")
    print(f"Crash/Recovery Events  : {len(recovered_jobs)} jobs intercepted and recovered")
    print(f"Terminal Failures      : {len(failed_jobs)}")
    print("-" * 70)
    print("LATENCY DISTRIBUTION (Nominal Path - Attempt 1):")
    print(f"  p50 : {calculate_percentile(nominal_latencies, 50):>6.3f}s")
    print(f"  p90 : {calculate_percentile(nominal_latencies, 90):>6.3f}s")
    print(f"  p95 : {calculate_percentile(nominal_latencies, 95):>6.3f}s")
    print(f"  p99 : {calculate_percentile(nominal_latencies, 99):>6.3f}s")
    print("-" * 70)
    if recovered_jobs:
        print("LATENCY DISTRIBUTION (Fault Recovery Path - SQS Redrive):")
        print(f"  p50 : {calculate_percentile(recovery_latencies, 50):>6.3f}s")
        print(f"  p95 : {calculate_percentile(recovery_latencies, 95):>6.3f}s")
        print(f"  p99 : {calculate_percentile(recovery_latencies, 99):>6.3f}s")
        print("-" * 70)
    print("LATENCY DISTRIBUTION (Blended System-Wide):")
    print(f"  p50 : {calculate_percentile(all_latencies, 50):>6.3f}s")
    print(f"  p95 : {calculate_percentile(all_latencies, 95):>6.3f}s")
    print(f"  p99 : {calculate_percentile(all_latencies, 99):>6.3f}s")
    print("="*70)

if __name__ == "__main__":
    main()