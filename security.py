import hashlib, hmac, secrets
from app.config import settings

def new_ticket_code() -> str:
    return "COS-" + secrets.token_hex(12).upper()

def ticket_signature(ticket_code: str, booking_reference: str) -> str:
    payload = f"{ticket_code}:{booking_reference}".encode()
    return hmac.new(settings.ticket_secret.encode(), payload, hashlib.sha256).hexdigest()

def fingerprint(payload: dict) -> str:
    # Stable canonical fingerprint binds an idempotency key to its original intent.
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
