import os
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Cosmic Ticketing", page_icon="🚀", layout="wide")
st.title("🚀 Cosmic Ticketing")
st.caption("Explore interstellar routes, reserve seats, and inspect your tickets.")

tabs = st.tabs(["Explore & Book", "My Booking", "Analytics"])
with tabs[0]:
    category = st.selectbox("Travel category", ["All", "GALACTIC_WORMHOLE", "INTER_DIMENSIONAL", "LIGHT_SPEED_CRUISER"])
    try:
        params = {"available_only": "true"}
        if category != "All": params["category"] = category
        services = requests.get(f"{API}/services", params=params, timeout=5).json()
        if not services:
            st.info("No matching services currently available.")
        for svc in services:
            with st.expander(f"{svc['name']} — {svc['source']} → {svc['destination']}"):
                st.write(f"**Category:** {svc['category']} | **Price:** {svc['price']} GC per seat")
                st.write(f"Departure: {svc['departure_at']} | Arrival: {svc['arrival_at']}")
                st.write(f"Seats available: {svc['available_seats']} / {svc['capacity']}")
                with st.form(f"book_{svc['id']}"):
                    customer = st.text_input("Customer name", key=f"name_{svc['id']}")
                    email = st.text_input("Email", key=f"email_{svc['id']}")
                    seats = st.number_input("Seats", min_value=1, max_value=min(20, svc['available_seats']), value=1, key=f"seats_{svc['id']}")
                    passengers = st.text_area("Passenger names (one per line)", value=customer, key=f"pass_{svc['id']}")
                    idem = st.text_input("Idempotency key (reuse only for retry)", key=f"idem_{svc['id']}", placeholder="e.g. booking-intent-123")
                    submitted = st.form_submit_button("Reserve tickets")
                    if submitted:
                        names = [n.strip() for n in passengers.splitlines() if n.strip()]
                        body = {"customer_name": customer, "customer_email": email, "service_id": svc['id'], "seats": int(seats), "passenger_names": names, "idempotency_key": idem}
                        try:
                            resp = requests.post(f"{API}/bookings", json=body, timeout=10)
                            if resp.ok:
                                st.success(f"Booking confirmed: {resp.json()['reference']}")
                                st.json(resp.json())
                            else: st.error(f"{resp.status_code}: {resp.text}")
                        except requests.RequestException as exc: st.error(str(exc))
    except requests.RequestException as exc:
        st.error(f"Cannot reach API at {API}: {exc}")
with tabs[1]:
    ref = st.text_input("Booking reference", placeholder="BK-...")
    if st.button("Find booking"):
        try:
            r = requests.get(f"{API}/bookings/{ref}", timeout=5)
            st.json(r.json()) if r.ok else st.error(r.text)
        except requests.RequestException as exc: st.error(str(exc))
    if ref and st.button("Cancel booking"):
        r = requests.post(f"{API}/bookings/{ref}/cancel", timeout=5)
        st.json(r.json()) if r.ok else st.error(r.text)
with tabs[2]:
    if st.button("Refresh analytics"):
        try: st.json(requests.get(f"{API}/analytics", timeout=5).json())
        except requests.RequestException as exc: st.error(str(exc))
