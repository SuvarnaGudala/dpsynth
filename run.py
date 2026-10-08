"""Entry point.  python run.py   |   WORKERS=4 python run.py (Linux/Mac)"""
import asyncio, multiprocessing as mp, sys
from app.config import PORT, WORKERS
from app.server import serve
def worker(): asyncio.run(serve(reuse=True))
if __name__ == "__main__":
    n = WORKERS if sys.platform != "win32" else 1
    print(f"DPSynth on http://localhost:{PORT}  workers={n}")
    if n == 1: asyncio.run(serve())
    else:
        ps = [mp.Process(target=worker) for _ in range(n)]
        [p.start() for p in ps]; [p.join() for p in ps]
