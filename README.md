# Cosmic Ticketing — Ticket Booking & Reservation System

**Author:** Karishma Singhi  
**Stack:** FastAPI, Pydantic, SQLAlchemy 2, SQLite, Streamlit, uv, Docker, pytest.

## 1. Project overview and assumptions

Cosmic Ticketing is a demo booking platform for futuristic travel services. It supports Galactic Wormhole Travel, Inter-Dimensional Travel, and Light-Speed Cruiser services. Users can search routes, inspect live seat availability, book single or group travel, retrieve/cancel reservations, verify signed tickets, consume tickets once, and view operational analytics.

Assumptions:
- `GC` means Galactic Credits; prices are stored as integer GC to avoid floating-point rounding.
- Each passenger in a booking receives a distinct ticket. This implementation reserves capacity, not named physical seat numbers.
- Services are created through the API; authentication/authorization and payment processing are out of scope for this assignment.
- `COMPLETED` is included in analytics schema but no scheduled departure worker is included to automatically transition bookings.
- SQLite is chosen for easy reproducibility and supports the conditional atomic seat update used here. For a high-throughput multi-instance deployment, PostgreSQL is recommended.

## 2. Architecture

- `app/main.py`: FastAPI routes, status codes, OpenAPI metadata and dependency wiring.
- `app/schemas.py`: Pydantic request/response validation.
- `app/models.py`: normalized SQLAlchemy entities, constraints and indexes.
- `app/services.py`: business logic for atomic reservations, idempotency, cancellation, ticket validation and analytics.
- `app/security.py`: random ticket codes, HMAC-SHA256 signatures and canonical request fingerprints.
- `app/database.py` / `app/config.py`: database session and environment configuration.
- `streamlit_app.py`: minimal user-facing search/booking/booking lookup/analytics UI.
- `tests/`: API, lifecycle, idempotency, ticket and concurrent booking tests.

Request flow: UI/client → FastAPI/Pydantic → business service → SQLAlchemy transaction → database. FastAPI serves interactive API docs at `/docs`.

## 3. Database design

- `travel_services`: route, category, schedule, capacity, remaining seats, integer price and service state.
- `bookings`: customer, service FK, requested seat count, total price, lifecycle state, unique reference, unique idempotency key and request fingerprint.
- `tickets`: one row per passenger, unique ticket code, booking FK, passenger name, HMAC signature, status and used timestamp.

Constraints/indexes include non-negative available seats bounded by capacity, positive booking seats, unique service name, unique booking reference, unique idempotency key, unique ticket code, foreign keys, and indexes on category/departure, service IDs, booking state and creation time. Booking and ticket entities are separated to represent group bookings without duplicating booking-level data.

## 4. Concurrency strategy

The key race is two transactions both reading (for example) two available seats and both deciding that two seats can be sold. A read-then-write implementation can oversell.

The implementation avoids using a prior availability read as the authority. Within the booking transaction it performs a conditional SQL update equivalent to:

```sql
UPDATE travel_services
SET available_seats = available_seats - :requested
WHERE id = :service_id
  AND available_seats >= :requested
  AND status = 'SCHEDULED';
```

The operation succeeds only when the database can apply the decrement while the predicate remains true. The affected-row count must be exactly one; otherwise the transaction returns a conflict. The decrement, booking insert and ticket inserts are in the same transaction, so a failed insert rolls back the capacity change. A database check constraint also ensures `0 <= available_seats <= capacity`.

For SQLite, writes are serialized by its locking model; the conditional update is the correctness boundary. For PostgreSQL, the same conditional update is atomic and row-level locking coordinates competing updates. A production system should add transaction retry/backoff for transient database lock errors and exercise the race test against its production database engine.

## 5. Duplicate booking strategy

Every booking request supplies an `idempotency_key`. It is unique in the database. A canonical SHA-256 fingerprint binds the key to the request intent. Retrying the same request with the same key returns the original booking and tickets. Reusing a key with a different payload returns HTTP 409. A uniqueness conflict is handled by checking whether an identical request committed concurrently.

Clients should generate a high-entropy key once per user booking intent and reuse it only for retries. This does not infer duplicates across independently generated keys; account authentication and business-specific duplicate heuristics would be needed for that.

## 6. Ticket security / anti-piracy

Ticket codes are generated from cryptographically secure random bytes. Each ticket is signed with HMAC-SHA256 over the ticket code and booking reference. Validation recomputes the signature and uses constant-time comparison, which makes edits to the ticket code/signature detectable without exposing the secret. `/tickets/validate` verifies without consuming; `/tickets/use` atomically changes `VALID` to `USED`, preventing successful reuse. Cancellation changes valid tickets to `CANCELLED`.

Limitations: the demo secret must be replaced in deployment; tickets are not encrypted; no QR renderer, authentication, audit trail, rate limiting, key rotation, or external identity check is included. The secret is server-side only and should be managed by a secret manager in production.

## 7. Testing strategy

Run `uv sync --extra dev` then `uv run pytest`. Tests cover service creation, schema validation, single/group booking, insufficient capacity, same-key retries, conflicting idempotency payloads, ticket signature/one-time use, cancellation rules and seat release, analytics, and a five-request concurrency race. The current suite contains six API-level tests, including the concurrent race scenario. The concurrency test asserts that only available capacity is sold and remaining seats never go negative.

## 8. Run with Docker

Requirements: Docker Engine and Docker Compose plugin.

```bash
# Optional: set a strong ticket secret in your shell
export TICKET_SECRET='replace-with-a-long-random-secret'
docker compose up --build
```

- API: http://localhost:8000
- Swagger / OpenAPI: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501
- Health: http://localhost:8000/health

SQLite data persists in the `cosmic_data` Docker volume. Stop with `Ctrl+C`; use `docker compose down`. To remove demo data too, run `docker compose down -v`.

## 9. API usage

Create a service:

```bash
curl -X POST http://localhost:8000/services \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Andromeda Express",
    "category":"GALACTIC_WORMHOLE",
    "source":"Luna Port",
    "destination":"Kepler-22",
    "departure_at":"2030-01-01T10:00:00Z",
    "arrival_at":"2030-01-01T12:00:00Z",
    "capacity":3,
    "price":100
  }'
```

Search: `GET /services?category=GALACTIC_WORMHOLE&available_only=true`

Book two passengers (replace service ID and use a fresh idempotency key):

```bash
curl -X POST http://localhost:8000/bookings \
  -H 'Content-Type: application/json' \
  -d '{
    "customer_name":"Ada Lovelace",
    "customer_email":"ada@example.com",
    "service_id":1,
    "seats":2,
    "passenger_names":["Ada Lovelace","Grace Hopper"],
    "idempotency_key":"ada-kepler-booking-0001"
  }'
```

Other endpoints:
- `GET /services/{service_id}` — service details and current availability.
- `GET /bookings/{reference}` — booking and tickets.
- `POST /bookings/{reference}/cancel` — cancel confirmed booking and release seats.
- `POST /tickets/validate` — body `{ "ticket_code": "...", "signature": "..." }`.
- `POST /tickets/use` — validate and consume a ticket exactly once.
- `GET /analytics` — totals, revenue, occupancy and category breakdown.
- `GET /docs` — interactive OpenAPI UI.

Common errors: `422` invalid schema, `404` unknown service/booking, `409` insufficient capacity, unavailable service, idempotency conflict or invalid lifecycle transition.

## 10. Design decisions, trade-offs and limitations

- SQLite keeps local setup simple; PostgreSQL is preferable for production and distributed traffic.
- Integer GC avoids float arithmetic.
- Conditional atomic decrement is simpler and portable compared with application-level locks, which do not coordinate across processes.
- Tickets use HMAC signatures and one-time state tracking, not a complete fraud platform.
- No authentication/authorization, payments, seat-map allocation, email delivery, scheduled expiration, or production observability is implemented.
- The sample UI is deliberately small; backend correctness and documentation take priority.
- API request/response schemas and endpoint descriptions are exposed through FastAPI OpenAPI.
