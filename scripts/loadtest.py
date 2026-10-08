"""Usage: python loadtest.py [total=100000] [concurrency=1000]"""
import asyncio, json, time, sys
T = int(sys.argv[1]) if len(sys.argv) > 1 else 100000; C = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
CSV = "age,city,income\n" + "\n".join(f"{20+i%40},{['Mumbai','Delhi','Pune','Chennai'][i%4]},{30000+i*700}" for i in range(60))
BODY = json.dumps(dict(csv=CSV, epsilon=1.0, n_out=50, plan="free")).encode()
REQ = b"POST /api/generate HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(BODY) + BODY
lat, ok, bad = [], 0, 0
async def worker(n):
    global ok, bad
    try: r, w = await asyncio.open_connection("127.0.0.1", 8000)
    except Exception: bad += n; return
    for _ in range(n):
        t = time.perf_counter()
        try:
            w.write(REQ); await w.drain(); st = await r.readline(); cl = 0
            while (h := await r.readline()) != b"\r\n":
                if h.lower().startswith(b"content-length"): cl = int(h.split(b":")[1])
            await r.readexactly(cl)
            if b"200" in st: ok += 1; lat.append(time.perf_counter() - t)
            else: bad += 1
        except Exception: bad += 1; return
    w.close()
async def main():
    t0 = time.time(); await asyncio.gather(*[worker(T // C) for _ in range(C)]); dt = time.time() - t0
    lat.sort(); p = lambda q: round(lat[int(len(lat) * q) - 1] * 1000, 1) if lat else 0
    print(json.dumps(dict(total=T, concurrency=C, ok=ok, failed=bad, seconds=round(dt, 1), rps=round(ok / dt), p50_ms=p(.5), p95_ms=p(.95), p99_ms=p(.99))))
asyncio.run(main())
