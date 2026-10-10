from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

def make_booking(client, service_id, key, seats=1, names=None):
    names = names or [f"Passenger {i+1}" for i in range(seats)]
    return client.post("/bookings", json={
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "service_id": service_id,
        "seats": seats,
        "passenger_names": names,
        "idempotency_key": key
    })

def test_service_search_and_successful_group_booking(client, service_payload):
    s = client.post("/services", json=service_payload)
    assert s.status_code == 201
    service_id = s.json()["id"]
    b = make_booking(client, service_id, "group-key-0001", 2, ["Ada", "Grace"])
    assert b.status_code == 201
    assert b.json()["seats"] == 2
    assert len(b.json()["tickets"]) == 2
    detail = client.get(f"/services/{service_id}").json()
    assert detail["available_seats"] == 1

def test_invalid_and_over_capacity_booking(client, service_payload):
    sid = client.post("/services", json=service_payload).json()["id"]
    bad = client.post("/bookings", json={"customer_name":"A", "customer_email":"bad", "service_id":sid, "seats":1, "passenger_names":["A"], "idempotency_key":"invalid-key-01"})
    assert bad.status_code == 422
    over = make_booking(client, sid, "over-key-0001", 4, ["A","B","C","D"])
    assert over.status_code == 409
    over2 = make_booking(client, sid, "over-key-0002", 3, ["A","B","C"])
    assert over2.status_code == 201
    no_seats = make_booking(client, sid, "over-key-0003", 1, ["D"])
    assert no_seats.status_code == 409

def test_idempotency_and_key_payload_conflict(client, service_payload):
    sid = client.post("/services", json=service_payload).json()["id"]
    first = make_booking(client, sid, "same-key-0001")
    retry = make_booking(client, sid, "same-key-0001")
    assert first.status_code == retry.status_code == 201
    assert first.json()["reference"] == retry.json()["reference"]
    changed = make_booking(client, sid, "same-key-0001", 2, ["A", "B"])
    assert changed.status_code == 409

def test_ticket_validation_one_time_use_and_cancel(client, service_payload):
    sid = client.post("/services", json=service_payload).json()["id"]
    b = make_booking(client, sid, "ticket-key-0001").json()
    ticket = b["tickets"][0]
    payload = {"ticket_code": ticket["ticket_code"], "signature": ticket["signature"]}
    assert client.post("/tickets/validate", json=payload).json()["valid"] is True
    assert client.post("/tickets/use", json=payload).json()["valid"] is True
    second_use = client.post("/tickets/use", json=payload).json()
    assert second_use["valid"] is False
    cancel = client.post(f"/bookings/{b['reference']}/cancel")
    assert cancel.status_code == 409

def test_cancel_releases_seats_and_analytics(client, service_payload):
    sid = client.post("/services", json=service_payload).json()["id"]
    b = make_booking(client, sid, "cancel-key-0001", 2, ["A", "B"]).json()
    cancelled = client.post(f"/bookings/{b['reference']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["seats_released"] == 2
    assert client.get(f"/services/{sid}").json()["available_seats"] == 3
    a = client.get("/analytics").json()
    assert a["total_bookings"] == 1
    assert a["cancelled_bookings"] == 1

def test_concurrent_booking_never_oversells(client, service_payload):
    # Five requests race for three seats. Exactly three seats should be allocated.
    sid = client.post("/services", json=service_payload).json()["id"]
    barrier = Barrier(5)
    def attempt(i):
        barrier.wait()
        return make_booking(client, sid, f"race-key-{i:04d}").status_code
    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(attempt, range(5)))
    assert statuses.count(201) == 3
    assert statuses.count(409) == 2
    assert client.get(f"/services/{sid}").json()["available_seats"] == 0
