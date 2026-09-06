"""Fresh DB: docker compose down -v && docker compose up --build; then python3 tests/promo_race_test.py"""
import concurrent.futures
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:8000"

def request(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())

def create(index):
    return request("/api/orders", "POST", {"sku":"KEY-CS2-PRIME", "promo_code":"LIMIT3", "order_id":f"promo_{uuid.uuid4().hex}_{index}"})

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
    results = list(pool.map(create, range(20)))

accepted = [body for status, body in results if status == 200]
assert len(accepted) <= 3, results
assert all(order["amount"] == 968 for order in accepted), accepted
assert all(status in {200, 409} for status, _ in results), results
print(f"PASS: LIMIT3 accepted {len(accepted)} of 20 concurrent orders (never more than 3).")
