#!/usr/bin/env python3
import http.server
import socketserver
import json
import os
import sys
import glob
import asyncio

# Ensure we use packages from virtual environment
site_packages_dirs = glob.glob(os.path.join(os.path.dirname(__file__), '.venv/lib/python3.*/site-packages'))
if site_packages_dirs:
    sys.path.insert(0, site_packages_dirs[0])

from rocketride import RocketRideClient

PORT = 8000
LOCAL_URI = "http://127.0.0.1:64836"
LOCAL_APIKEY = "dummy"

# Map public tokens to project info so we can resolve task tokens dynamically
TOKEN_MAP = {
    "pk_d730b605e0c6546309f632326e4f1501": ("66897336-08ca-46c7-87df-e07050a37edd", "webhook_1"), # Triage
    "pk_1ff0b8f60d86aa4d1ce799d78cef0221": ("6a470728-d1e6-42bf-a6f5-f67da920e11e", "webhook_1"), # Verdict
    "pk_63921897c45422060cabefac7d291e9c": ("e0bfa150-672d-4ff7-9416-29229324e818", "webhook_1"), # Audit
}

async def forward_request(project_id, source, payload):
    # Load .env variables so substitution in local engine works
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

    uri = os.environ.get('ROCKETRIDE_URI', LOCAL_URI)
    apikey = os.environ.get('ROCKETRIDE_APIKEY', LOCAL_APIKEY)

    client = RocketRideClient(uri, auth=apikey)
    await client.connect()
    try:
        # Get active task token for this project
        task_token = await client.get_task_token(project_id, source)
        if not task_token:
            raise RuntimeError(f"No active task running for project {project_id}")
        
        # Send data to the pipeline via WebSocket/DAP
        print(f"Forwarding payload to task token: {task_token}...")
        response = await client.send(task_token, payload, mimetype='text/plain')
        return response
    finally:
        await client.disconnect()

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
            token = auth_header.replace("Bearer ", "").strip()

            if token not in TOKEN_MAP:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid or unmapped token: {token}"}).encode())
                return

            project_id, source = TOKEN_MAP[token]
            print(f"Received request for {token} (Project: {project_id})")

            # Run async forwarding synchronously
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(forward_request(project_id, source, post_data))
                loop.close()

                # Wrap result in the cloud gateway shape index.html expects
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
                print(f"Error forwarding request: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            super().do_POST()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

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
