"""Exhausts one test SKU, restocks it, then concurrently retries the same order."""
import concurrent.futures
import json
import time
import urllib.request
import uuid

BASE = "http://localhost:8000"
SKU, AMOUNT = "KEY-EFT", 3490

def request(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read())

for provider in ("A", "B"):
    request(f"/api/admin/providers/{provider}", "PUT", {"mode":"success", "error_rate":0, "timeout_rate":0, "delay_ms":0})

target = None
for index in range(15):
    order_id = f"recovery_{uuid.uuid4().hex}_{index}"
    request("/api/orders", "POST", {"sku":SKU, "order_id":order_id})
    request("/api/webhooks/payment", "POST", {"event_id":f"evt_{order_id}", "order_id":order_id, "status":"paid", "amount":AMOUNT})
    for _ in range(30):
        order = request(f"/api/orders/{order_id}")
        if order["status"] in {"delivered", "out_of_stock", "delivery_failed"}:
            break
        time.sleep(.1)
    if order["status"] == "out_of_stock":
        target = order
        break

assert target and target["status"] == "out_of_stock", target
request(f"/api/admin/inventory/{SKU}", "POST", {"count":1})
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(lambda _: request(f"/api/admin/orders/{target['id']}/retry", "POST"), range(2)))
result = request(f"/api/orders/{target['id']}")
assert result["status"] == "delivered" and result["code"], result
print("PASS: empty-pool order was restocked and concurrently retried with one delivered key:", result["code"])
