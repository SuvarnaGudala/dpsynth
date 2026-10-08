"""DPSynth Production Asyncio HTTP Server & ASGI Application.
Provides:
- High-performance pure-asyncio raw HTTP 1.1 keep-alive server (for zero-dependency runtime & load testing)
- Exported `serve()` function for multi-process worker scaling in run.py
- Production ASGI `app` compatible with Uvicorn, Gunicorn, and Docker deployments
"""
import asyncio
import os
import socket
import sys
import time
from .config import PORT, HOST, STATIC
from .handlers import route
from .db import writer as db_writer

# ----------------- Pure Asyncio HTTP Server -----------------

async def handle_http_connection(reader, writer):
    """Handles an HTTP 1.1 keep-alive connection with request pipelining support."""
    try:
        while True:
            # 1. Read HTTP Request Headers
            try:
                header_data = await reader.readuntil(b"\r\n\r\n")
            except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
                break

            lines = header_data.decode("utf-8", errors="replace").split("\r\n")
            if not lines or not lines[0]:
                break

            parts = lines[0].split(" ")
            if len(parts) < 2:
                break
            method, full_path = parts[0], parts[1]

            # Parse headers into dict
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            # 2. Read Request Body if Content-Length present
            content_length = int(headers.get("content-length", 0))
            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            # 3. Route Request
            path = full_path.split("?")[0]
            try:
                status_code, response_data, content_type = route(method, full_path, body_bytes, headers)
            except Exception as e:
                err_body = f'{{"error": "Internal server error: {str(e)}"}}'.encode("utf-8")
                status_code, response_data, content_type = 500, err_body, "application/json"

            # 4. Formulate HTTP 1.1 Response
            status_text = {
                200: "OK", 201: "Created", 400: "Bad Request",
                401: "Unauthorized", 402: "Payment Required",
                403: "Forbidden", 404: "Not Found", 500: "Internal Server Error"
            }.get(status_code, "OK")

            is_close = headers.get("connection", "").lower() == "close"
            conn_header = "close" if is_close else "keep-alive"

            header_resp = (
                f"HTTP/1.1 {status_code} {status_text}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(response_data)}\r\n"
                f"Connection: {conn_header}\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"Access-Control-Allow-Headers: Content-Type, Authorization, X-API-Key\r\n"
                f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                f"Server: DPSynth-Engine/2.0\r\n"
                f"\r\n"
            ).encode("utf-8")

            writer.write(header_resp + response_data)
            await writer.drain()

            if is_close:
                break
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def serve(host=HOST, port=PORT, reuse=False):
    """
    Main entry point for starting the asyncio server.
    Starts background DB commit worker and binds socket with reuse settings.
    """
    # Start async background batch writer for non-blocking disk operations
    asyncio.create_task(db_writer())

    sock = None
    if reuse and sys.platform != "win32":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind((host, port))
        sock.listen(4096)
        sock.setblocking(False)

    if sock:
        server = await asyncio.start_server(handle_http_connection, sock=sock, backlog=4096)
    else:
        server = await asyncio.start_server(handle_http_connection, host, port, backlog=4096)

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"DPSynth Production Server listening on {addrs} (PID: {os.getpid()})")
    async with server:
        await server.serve_forever()

# ----------------- Production ASGI App (FastAPI / Starlette) -----------------

try:
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.staticfiles import StaticFiles

    async def asgi_bridge(request: Request):
        method = request.method
        full_path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        body_bytes = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        
        status_code, resp_bytes, content_type = route(method, full_path, body_bytes, headers)
        return Response(
            content=resp_bytes,
            status_code=status_code,
            media_type=content_type.split(";")[0],
            headers={"Content-Type": content_type}
        )

    # Exported ASGI app for `uvicorn app.server:app`
    app = Starlette(
        debug=False,
        routes=[
            Route("/health", asgi_bridge, methods=["GET"]),
            Route("/api/{rest:path}", asgi_bridge, methods=["GET", "POST", "OPTIONS"]),
            Route("/", asgi_bridge, methods=["GET"]),
            Mount("/static", StaticFiles(directory=STATIC), name="static")
        ]
    )
except ImportError:
    # Minimal fallback ASGI app if starlette not present
    async def app(scope, receive, send):
        if scope["type"] == "http":
            req_headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            body = b""
            while True:
                msg = await receive()
                body += msg.get("body", b"")
                if not msg.get("more_body", False):
                    break
            path = scope["path"] + (f"?{scope['query_string'].decode()}" if scope.get("query_string") else "")
            status, data, ctype = route(scope["method"], path, body, req_headers)
            await send({
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", ctype.encode()),
                    (b"content-length", str(len(data)).encode()),
                    (b"server", b"DPSynth/2.0")
                ]
            })
            await send({"type": "http.response.body", "body": data})

if __name__ == "__main__":
    asyncio.run(serve())