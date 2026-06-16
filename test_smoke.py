"""Smoke test the web dashboard server"""
import sys, os, time, threading, json
_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(_root)
sys.path.insert(0, _root)

os.environ['PYTHONIOENCODING'] = 'utf-8'

print("Testing server startup...", flush=True)

from src.web_dashboard.server import app

# Print routes
print("Routes:", [r.rule for r in app.url_map.iter_rules()], flush=True)

# Run server in thread
def run():
    app.run(host='127.0.0.1', port=16234, debug=False, use_reloader=False)

t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(2)

# Test HTTP endpoints
import urllib.request
try:
    # Root page
    resp = urllib.request.urlopen('http://127.0.0.1:16234/', timeout=5)
    print(f"GET / -> {resp.status} ({len(resp.read())} bytes)", flush=True)
    
    # API status
    resp = urllib.request.urlopen('http://127.0.0.1:16234/api/status', timeout=5)
    data = json.loads(resp.read())
    print(f"GET /api/status -> {data}", flush=True)
    
    # API tasks
    resp = urllib.request.urlopen('http://127.0.0.1:16234/api/tasks', timeout=5)
    data = json.loads(resp.read())
    print(f"GET /api/tasks -> {len(data)} tasks", flush=True)
    
    print("\nAll smoke tests PASSED!", flush=True)
except Exception as e:
    print(f"FAILED: {e}", flush=True)
