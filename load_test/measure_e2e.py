# load_test/measure_e2e.py
import time
import requests
import statistics
import subprocess

# Pull endpoint dynamically from terraform output
api = subprocess.check_output(
    ["terraform", "-chdir=terraform", "output", "-raw", "api_endpoint"]
).decode("utf-8").strip().rstrip("/")

latencies = []
total_jobs = 50
print(f"Running end-to-end benchmark for {total_jobs} jobs against {api}...")

for i in range(total_jobs):
    t0 = time.time()
    
    # 1. Submit job
    r = requests.post(
        f"{api}/jobs",
        json={
            "s3_key": "uploads/pretest.jpg",
            "operation": "resize",
            "params": {"width": 200},
        }
    )
    if r.status_code not in (200, 202):
        print(f"Job submission {i+1} failed ({r.status_code}): {r.text}")
        continue
        
    job_id = r.json()["job_id"]
    
    # 2. Poll status endpoint until COMPLETED
    while True:
        res = requests.get(f"{api}/jobs/{job_id}").json()
        status = res.get("status") or res.get("job_status")
        if status == "COMPLETED":
            latencies.append(time.time() - t0)
            break
        elif status == "FAILED":
            print(f"Job {job_id} marked as FAILED in DynamoDB!")
            break
        time.sleep(0.5)

    if (i + 1) % 10 == 0:
        print(f"Completed {i + 1}/{total_jobs} jobs...")

if latencies:
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    print("\n================ Latency Results ================")
    print(f"Total jobs measured: {len(latencies)}")
    print(f"p50: {p50:.2f}s")
    print(f"p95: {p95:.2f}s")
    print(f"p99: {p99:.2f}s")
    print("=================================================")