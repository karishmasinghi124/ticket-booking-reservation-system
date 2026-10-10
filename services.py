from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models import TravelService, Booking, Ticket
from app.schemas import BookingCreate, ServiceCreate
from app.security import new_ticket_code, ticket_signature, fingerprint, safe_equal

def create_service(db: Session, data: ServiceCreate):
    service = TravelService(**data.model_dump(), available_seats=data.capacity, status="SCHEDULED")
    db.add(service)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A service with this name already exists")
    db.refresh(service)
    return service

def create_booking(db: Session, data: BookingCreate):
    raw = data.model_dump(mode="json")
    fp = fingerprint({k: v for k, v in raw.items() if k != "idempotency_key"})
    existing = db.scalar(select(Booking).options(joinedload(Booking.tickets)).where(Booking.idempotency_key == data.idempotency_key))
    if existing:
        db.rollback()
        if existing.request_fingerprint != fp:
            raise HTTPException(409, "Idempotency key was already used for a different booking request")
        return existing

    # The initial lookup starts SQLAlchemy's transaction (autobegin). Keep the
    # atomic seat decrement, booking row and tickets inside that same transaction.
    try:
        result = db.execute(
            update(TravelService)
            .where(
                TravelService.id == data.service_id,
                TravelService.available_seats >= data.seats,
                TravelService.status == "SCHEDULED",
            )
            .values(available_seats=TravelService.available_seats - data.seats)
        )
        if result.rowcount != 1:
            service = db.get(TravelService, data.service_id)
            db.rollback()
            if service is None:
                raise HTTPException(404, "Travel service not found")
            if service.status != "SCHEDULED":
                raise HTTPException(409, "Travel service is not available for booking")
            raise HTTPException(409, "Not enough seats available")
        service = db.get(TravelService, data.service_id)
        booking = Booking(
            reference="BK-" + __import__("secrets").token_hex(8).upper(),
            customer_name=data.customer_name.strip(),
            customer_email=str(data.customer_email).lower(),
            service_id=data.service_id,
            seats=data.seats,
            total_price=service.price * data.seats,
            status="CONFIRMED",
            idempotency_key=data.idempotency_key,
            request_fingerprint=fp,
        )
        db.add(booking)
        db.flush()
        for passenger_name in data.passenger_names:
            code = new_ticket_code()
            db.add(Ticket(
                ticket_code=code,
                booking_id=booking.id,
                passenger_name=passenger_name.strip(),
                status="VALID",
                signature=ticket_signature(code, booking.reference),
            ))
        db.flush()
        booking_id = booking.id
        db.commit()
        return db.scalar(select(Booking).options(joinedload(Booking.tickets)).where(Booking.id == booking_id))
    except IntegrityError:
        db.rollback()
        # Another identical request may have committed while this request waited.
        existing = db.scalar(select(Booking).options(joinedload(Booking.tickets)).where(Booking.idempotency_key == data.idempotency_key))
        if existing and existing.request_fingerprint == fp:
            db.rollback()
            return existing
        db.rollback()
        raise HTTPException(409, "Booking conflict; retry with the same idempotency key")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

def get_booking(db: Session, reference: str):
    booking = db.scalar(select(Booking).options(joinedload(Booking.tickets)).where(Booking.reference == reference))
    if not booking:
        raise HTTPException(404, "Booking not found")
    return booking

def cancel_booking(db: Session, reference: str):
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if not booking:
        db.rollback()
        raise HTTPException(404, "Booking not found")
    if booking.status == "CANCELLED":
        db.rollback()
        return {"reference": reference, "status": "CANCELLED", "seats_released": 0}
    if booking.status != "CONFIRMED":
        db.rollback()
        raise HTTPException(409, f"Cannot cancel a booking in {booking.status} state")

    booking_id, seats, service_id = booking.id, booking.seats, booking.service_id
    try:
        # Conditional state transition prevents two concurrent cancellation
        # requests from releasing the same capacity twice. The NOT EXISTS
        # condition also blocks cancellation if a ticket has already been used.
        used_ticket_exists = select(Ticket.id).where(
            Ticket.booking_id == booking_id, Ticket.status == "USED"
        ).exists()
        changed = db.execute(
            update(Booking)
            .where(Booking.id == booking_id, Booking.status == "CONFIRMED", ~used_ticket_exists)
            .values(status="CANCELLED")
        )
        if changed.rowcount != 1:
            db.rollback()
            latest = db.scalar(select(Booking).where(Booking.reference == reference))
            if latest and latest.status == "CANCELLED":
                db.rollback()
                return {"reference": reference, "status": "CANCELLED", "seats_released": 0}
            db.rollback()
            raise HTTPException(409, "Cannot cancel: booking changed state or a ticket has already been used")
        db.execute(update(Ticket).where(Ticket.booking_id == booking_id, Ticket.status == "VALID").values(status="CANCELLED"))
        db.execute(update(TravelService).where(TravelService.id == service_id).values(available_seats=TravelService.available_seats + seats))
        db.commit()
        return {"reference": reference, "status": "CANCELLED", "seats_released": seats}
    except Exception:
        db.rollback()
        raise

def validate_ticket(db: Session, ticket_code: str, signature: str, consume: bool = False):
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_code == ticket_code))
    if not ticket:
        return {"valid": False, "status": "UNKNOWN", "message": "Ticket does not exist", "ticket_code": ticket_code}
    booking = db.get(Booking, ticket.booking_id)
    expected = ticket_signature(ticket.ticket_code, booking.reference)
    if not safe_equal(expected, signature) or not safe_equal(ticket.signature, signature):
        return {"valid": False, "status": "INVALID_SIGNATURE", "message": "Ticket signature is invalid", "ticket_code": ticket_code}
    if booking.status != "CONFIRMED" or ticket.status != "VALID":
        return {"valid": False, "status": ticket.status, "message": "Ticket is cancelled or has already been used", "ticket_code": ticket_code}
    if consume:
        # A conditional update ensures a ticket can only be consumed once.
        result = db.execute(update(Ticket).where(Ticket.id == ticket.id, Ticket.status == "VALID").values(status="USED", used_at=datetime.now(timezone.utc)))
        if result.rowcount != 1:
            db.rollback()
            return {"valid": False, "status": "USED", "message": "Ticket has already been used", "ticket_code": ticket_code}
        db.commit()
        return {"valid": True, "status": "USED", "message": "Ticket validated and marked as used", "ticket_code": ticket_code}
    return {"valid": True, "status": "VALID", "message": "Ticket signature verified; ticket is unused", "ticket_code": ticket_code}

def analytics(db: Session):
    bookings = db.scalars(select(Booking)).all()
    services = {s.id: s for s in db.scalars(select(TravelService)).all()}
    active = [b for b in bookings if b.status == "CONFIRMED"]
    total_capacity = sum(s.capacity for s in services.values())
    available = sum(s.available_seats for s in services.values())
    by_category, revenue_by_category = defaultdict(int), defaultdict(int)
    for b in bookings:
        category = services[b.service_id].category
        if b.status != "CANCELLED":
            by_category[category] += 1
            if b.status in ("CONFIRMED", "COMPLETED"):
                revenue_by_category[category] += b.total_price
    return {
        "total_bookings": len(bookings),
        "active_bookings": len(active),
        "tickets_sold": sum(b.seats for b in bookings if b.status in ("CONFIRMED", "COMPLETED")),
        "revenue_gc": sum(b.total_price for b in bookings if b.status in ("CONFIRMED", "COMPLETED")),
        "occupancy_percent": round(((total_capacity - available) / total_capacity * 100), 2) if total_capacity else 0.0,
        "average_booking_size": round(sum(b.seats for b in bookings) / len(bookings), 2) if bookings else 0.0,
        "single_bookings": sum(1 for b in bookings if b.seats == 1 and b.status != "CANCELLED"),
        "group_bookings": sum(1 for b in bookings if b.seats > 1 and b.status != "CANCELLED"),
        "cancelled_bookings": sum(1 for b in bookings if b.status == "CANCELLED"),
        "completed_bookings": sum(1 for b in bookings if b.status == "COMPLETED"),
        "bookings_by_category": dict(by_category),
        "revenue_by_category": dict(revenue_by_category),
    }
