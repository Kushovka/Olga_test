"""Second-stage concurrency check. Run after `docker compose up --build`.

It exhausts one SKU, restores exactly one key, and sends two checkout requests
at once. PostgreSQL row locks must leave one reservation and one sold-out reply.
"""
import concurrent.futures
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:8000"
SKU = "KEY-CS2-PRIME"


def request(path, method="GET", body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=payload, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


_, products = request("/api/products")
available = next(item["available"] for item in products if item["sku"] == SKU)
for number in range(available):
    status, _ = request("/api/orders", "POST", {"sku": SKU, "order_id": f"drain_{uuid.uuid4().hex[:18]}_{number}"})
    assert status == 200, status

# The pool is now empty. Restore precisely one sellable unit.
status, result = request(f"/api/admin/inventory/{SKU}", "POST", {"count": 1})
assert status == 200 and result["added"] == 1, result

def checkout(buyer):
    return request("/api/orders", "POST", {"sku": SKU, "order_id": f"last_unit_{uuid.uuid4().hex[:20]}_{buyer}"})

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(checkout, ("first", "second")))

codes = sorted(status for status, _ in results)
assert codes == [200, 409], results
winner = next(body for status, body in results if status == 200)
loser = next(body for status, body in results if status == 409)
assert winner["status"] == "reserved" and winner["reservation_expires_at"], winner
assert "раскупили" in loser["detail"].lower(), loser
print("PASS: exactly one buyer reserved the last key; the other received a clear sold-out response.")
