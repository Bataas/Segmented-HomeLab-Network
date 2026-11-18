#!/usr/bin/env python3
"""
speedtest_multistream.py
========================
Multi-stream HTTP/HTTPS download & upload throughput benchmark utility
used during Phase E to test multi-queue TCP saturation through pfSense.
"""

import time
import urllib.request
import http.client
import ssl
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}


def download_worker(duration=8.0):
    end_time = time.perf_counter() + duration
    total_bytes = 0
    while time.perf_counter() < end_time:
        req = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=25000000", headers=headers)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                while time.perf_counter() < end_time:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
        except Exception:
            break
    return total_bytes


def upload_worker(duration=8.0):
    end_time = time.perf_counter() + duration
    total_bytes = 0
    payload = b"0" * (512 * 1024)
    conn = http.client.HTTPSConnection("speed.cloudflare.com", context=ctx, timeout=10)
    try:
        while time.perf_counter() < end_time:
            conn.request("POST", "/__up", body=payload, headers=headers)
            resp = conn.getresponse()
            resp.read()
            total_bytes += len(payload)
    except Exception:
        pass
    finally:
        conn.close()
    return total_bytes


def run_benchmark(streams=8, duration=8.0):
    print(f"Running {streams}-stream Download test ({duration}s)...")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=streams) as ex:
        futs = [ex.submit(download_worker, duration) for _ in range(streams)]
        dl_bytes = sum(f.result() for f in futs)
    dl_elapsed = time.perf_counter() - t0
    dl_mbps = (dl_bytes * 8) / (dl_elapsed * 1_000_000)
    print(f"Download: {dl_mbps:.2f} Mbps ({dl_bytes / (1024*1024):.1f} MB in {dl_elapsed:.2f}s)")

    print(f"Running {streams}-stream Upload test ({duration}s)...")
    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=streams) as ex:
        futs = [ex.submit(upload_worker, duration) for _ in range(streams)]
        ul_bytes = sum(f.result() for f in futs)
    ul_elapsed = time.perf_counter() - t1
    ul_mbps = (ul_bytes * 8) / (ul_elapsed * 1_000_000)
    print(f"Upload:   {ul_mbps:.2f} Mbps ({ul_bytes / (1024*1024):.1f} MB in {ul_elapsed:.2f}s)")


if __name__ == "__main__":
    run_benchmark(streams=8, duration=8.0)
