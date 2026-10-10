from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class TravelService(Base):
    __tablename__ = "travel_services"
    __table_args__ = (
        CheckConstraint("capacity >= 0", name="ck_service_capacity"),
        CheckConstraint("available_seats >= 0 AND available_seats <= capacity", name="ck_service_available"),
        Index("ix_services_category_departure", "category", "departure_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    source: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    arrival_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer)
    available_seats: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)  # integer units of Galactic Credits (GC)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("seats > 0", name="ck_booking_seats_positive"),
        Index("ix_bookings_created_at", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_email: Mapped[str] = mapped_column(String(254), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("travel_services.id", ondelete="RESTRICT"), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    service: Mapped["TravelService"] = relationship(back_populates="bookings")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="booking", cascade="all, delete-orphan")

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("ticket_code", name="uq_ticket_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    passenger_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="VALID", index=True)
    signature: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booking: Mapped["Booking"] = relationship(back_populates="tickets")
