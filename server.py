#!/usr/bin/env python3
"""
Local dev bridge server for FinComp Check.

The RocketRide SDK only returns actual pipeline answers (not just a receipt)
when the SAME client connection that started the pipeline also sends the data.
On startup this server:
  1. Connects a persistent RocketRide client
  2. Terminates any existing tasks for each pipeline project
  3. Starts fresh pipeline tasks on that client (so it "owns" them)
  4. Subsequent /webhook POSTs reuse those task tokens on the same connection,
     so client.send() waits for and returns the full answers payload.
"""
import http.server
import socketserver
import json
import os
import sys
import glob
import asyncio
import threading

# Ensure we use packages from virtual environment
site_packages_dirs = glob.glob(os.path.join(os.path.dirname(__file__), '.venv/lib/python3.*/site-packages'))
if site_packages_dirs:
    sys.path.insert(0, site_packages_dirs[0])

from rocketride import RocketRideClient

PORT = 8000
LOCAL_URI = "http://127.0.0.1:64836"
LOCAL_APIKEY = "dummy"

# Pipeline files for each public token
PIPELINES = [
    {
        "public_token": "pk_d730b605e0c6546309f632326e4f1501",
        "file": "fincomp-triage.pipe",
        "label": "Triage",
    },
    {
        "public_token": "pk_1ff0b8f60d86aa4d1ce799d78cef0221",
        "file": "fincomp-verdict.pipe",
        "label": "Verdict",
    },
    {
        "public_token": "pk_63921897c45422060cabefac7d291e9c",
        "file": "fincomp-audit.pipe",
        "label": "Audit",
    },
]

# ------------------------------------------------------------------
# Runtime state
# ------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop = None
_client: RocketRideClient = None
_task_tokens: dict = {}          # public_token -> task_token (tk_...)
_client_ready = threading.Event()

def _load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

async def _start_pipelines():
    """Terminate old tasks, start fresh ones owned by this client."""
    global _task_tokens
    for p in PIPELINES:
        path = p["file"]
        if not os.path.exists(path):
            print(f"  WARNING: {path} not found — skipping")
            continue
        with open(path) as f:
            pipeline_def = json.load(f)
        pipeline_config = pipeline_def.get("pipeline", pipeline_def)
        project_id = pipeline_config.get("project_id")
        source = pipeline_config.get("source", "webhook_1")

        # Terminate any existing task so we can start fresh
        try:
            old_token = await _client.get_task_token(project_id, source)
            if old_token:
                print(f"  Terminating old {p['label']} task {old_token[:20]}...")
                await _client.terminate(old_token)
                await asyncio.sleep(1)
        except Exception as e:
            print(f"  (no old task to terminate for {p['label']}: {e})")

        # Start a fresh pipeline — THIS client owns it, so send() returns answers
        print(f"  Starting {p['label']} ({path})...")
        result = await _client.use(pipeline=pipeline_config, ttl=0)
        task_token = result["token"]
        _task_tokens[p["public_token"]] = task_token
        # Subscribe to events so result events arrive on this connection
        await _client.set_events(token=task_token, event_types=["ALL"])
        print(f"  {p['label']} ready. Token: {task_token[:20]}...")

    await asyncio.sleep(3)  # let pipelines finish booting
    print("All pipelines started and owned by this client.")

async def _init_client():
    global _client
    _load_env()
    uri = os.environ.get('ROCKETRIDE_URI', LOCAL_URI)
    apikey = os.environ.get('ROCKETRIDE_APIKEY', LOCAL_APIKEY)
    _client = RocketRideClient(uri, auth=apikey)
    await _client.connect()
    print(f"Persistent RocketRide client connected to {uri}")

    await _start_pipelines()
    _client_ready.set()

    # Keep the event loop alive
    await asyncio.Event().wait()

def _start_background_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_init_client())

# Start background thread
_bg_thread = threading.Thread(target=_start_background_loop, daemon=True)
_bg_thread.start()

def run_in_loop(coro):
    """Submit a coroutine to the background event loop and block until done."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=180)

async def forward_request(public_token, payload):
    task_token = _task_tokens.get(public_token)
    if not task_token:
        raise RuntimeError(f"No task token found for public token {public_token}")

    print(f"Sending to {task_token[:20]}...")
    response = await asyncio.wait_for(
        _client.send(task_token, payload, mimetype='text/plain'),
        timeout=170
    )
    keys = list(response.keys()) if isinstance(response, dict) else type(response)
    print(f"Result keys: {keys}")
    return response

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        if self.path == "/webhook":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            auth_header = self.headers.get("Authorization", "")
            public_token = auth_header.replace("Bearer ", "").strip()

            if public_token not in _task_tokens and not any(p["public_token"] == public_token for p in PIPELINES):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Unknown token: {public_token}"}).encode())
                return

            print(f"Received request for {public_token[:20]}...")

            # Wait for pipelines to be ready (up to 60s at boot time)
            if not _client_ready.wait(timeout=60):
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Pipelines not yet ready"}).encode())
                return

            try:
                result = run_in_loop(forward_request(public_token, post_data))

                wrapped_response = {
                    "data": {
                        "objects": {
                            "body": result
                        }
                    }
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(wrapped_response).encode())
            except Exception as e:
                print(f"Error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            super().do_POST()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Suppress noisy access logs

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Local dev bridge server started at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            sys.exit(0)

if __name__ == '__main__':
    run()
