from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.database import Base, engine, get_db
from app.models import TravelService, Booking
from app.schemas import ServiceCreate, ServiceOut, BookingCreate, BookingOut, CancelOut, ValidateTicketIn, TicketValidationOut, AnalyticsOut
from app.services import create_service, create_booking, get_booking, cancel_booking, validate_ticket, analytics

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="Cosmic Ticketing API",
    version="1.0.0",
    description="Futuristic travel booking with atomic seat reservation, idempotency, signed tickets and analytics.",
    lifespan=lifespan,
)

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}

@app.post("/services", response_model=ServiceOut, status_code=201, tags=["services"], summary="Create a travel service")
def add_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    """Create a scheduled service. Category must be one of the three supported travel types."""
    return create_service(db, payload)

@app.get("/services", response_model=list[ServiceOut], tags=["services"], summary="Search travel services")
def list_services(
    category: str | None = Query(None, description="GALACTIC_WORMHOLE, INTER_DIMENSIONAL, LIGHT_SPEED_CRUISER"),
    source: str | None = None,
    destination: str | None = None,
    departure_after: datetime | None = None,
    departure_before: datetime | None = None,
    available_only: bool = True,
    db: Session = Depends(get_db),
):
    q = select(TravelService)
    if category:
        q = q.where(TravelService.category == category.upper())
    if source:
        q = q.where(TravelService.source.ilike(f"%{source}%"))
    if destination:
        q = q.where(TravelService.destination.ilike(f"%{destination}%"))
    if departure_after:
        q = q.where(TravelService.departure_at >= departure_after)
    if departure_before:
        q = q.where(TravelService.departure_at <= departure_before)
    if available_only:
        q = q.where(TravelService.available_seats > 0, TravelService.status == "SCHEDULED")
    return db.scalars(q.order_by(TravelService.departure_at)).all()

@app.get("/services/{service_id}", response_model=ServiceOut, tags=["services"])
def service_details(service_id: int, db: Session = Depends(get_db)):
    service = db.get(TravelService, service_id)
    if not service:
        raise HTTPException(404, "Travel service not found")
    return service

@app.post("/bookings", response_model=BookingOut, status_code=201, tags=["bookings"], summary="Book one or more seats")
def book(payload: BookingCreate, db: Session = Depends(get_db)):
    """Send a stable Idempotency-Key in the request body; retries with the same intent return the original booking."""
    return create_booking(db, payload)

@app.get("/bookings/{reference}", response_model=BookingOut, tags=["bookings"])
def booking_details(reference: str, db: Session = Depends(get_db)):
    return get_booking(db, reference)

@app.post("/bookings/{reference}/cancel", response_model=CancelOut, tags=["bookings"])
def cancel(reference: str, db: Session = Depends(get_db)):
    return cancel_booking(db, reference)

@app.post("/tickets/validate", response_model=TicketValidationOut, tags=["tickets"], summary="Verify ticket signature without consuming it")
def ticket_validate(payload: ValidateTicketIn, db: Session = Depends(get_db)):
    return validate_ticket(db, payload.ticket_code, payload.signature, consume=False)

@app.post("/tickets/use", response_model=TicketValidationOut, tags=["tickets"], summary="Validate and consume a ticket once")
def ticket_use(payload: ValidateTicketIn, db: Session = Depends(get_db)):
    return validate_ticket(db, payload.ticket_code, payload.signature, consume=True)

@app.get("/analytics", response_model=AnalyticsOut, tags=["analytics"])
def get_analytics(db: Session = Depends(get_db)):
    return analytics(db)
