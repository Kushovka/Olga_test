"""Run after `docker compose up --build`: python3 tests/race_test.py"""
import concurrent.futures
import json
import urllib.request
import uuid

BASE = "http://localhost:8000"

def request(path, method="GET", body=None):
    payload = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE + path, data=payload, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())

idem_id = "idem_" + uuid.uuid4().hex[:12]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    duplicate_orders = list(pool.map(lambda _: request("/api/orders", "POST", {"sku": "SUB-DISCORD-1M", "order_id": idem_id}), range(2)))
assert {item["id"] for item in duplicate_orders} == {idem_id}, duplicate_orders

order_id = "race_" + uuid.uuid4().hex[:12]
order = request("/api/orders", "POST", {"sku": "KEY-CS2-PRIME", "order_id": order_id})
print("Created", order["id"])

# A forged/incorrect paid event must be stored but never release a code.
request("/api/webhooks/payment", "POST", {"event_id": f"evt_bad_{order_id}", "order_id": order_id, "status": "paid", "amount": 1})
import time; time.sleep(.2)
assert request(f"/api/orders/{order_id}")["status"] == "created", "amount mismatch incorrectly confirmed payment"

def send_webhook(index):
    return request("/api/webhooks/payment", "POST", {"event_id": f"evt_{order_id}_{index}", "order_id": order_id, "status": "paid", "amount": 1290})

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
    list(pool.map(send_webhook, range(50)))

# Allow the in-process webhook task to finish, then assert one visible delivery.
time.sleep(1)
result = request(f"/api/orders/{order_id}")
assert result["status"] == "delivered" and result["code"], result
duplicate = request("/api/webhooks/payment", "POST", {"event_id": f"evt_{order_id}_0", "order_id": order_id, "status": "paid", "amount": 1290})
after = request(f"/api/orders/{order_id}")
assert duplicate["duplicate"] and after["code"] == result["code"], (duplicate, result, after)
print("PASS: 50 concurrent paid events produced exactly one delivered code:", result["code"])
