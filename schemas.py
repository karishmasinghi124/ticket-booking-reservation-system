from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, EmailStr, model_validator
from typing import Literal

Category = Literal["GALACTIC_WORMHOLE", "INTER_DIMENSIONAL", "LIGHT_SPEED_CRUISER"]

class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: Category
    source: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    departure_at: datetime
    arrival_at: datetime
    capacity: int = Field(gt=0, le=10000)
    price: int = Field(ge=0, le=10**9)

    @model_validator(mode="after")
    def dates_make_sense(self):
        if self.arrival_at <= self.departure_at:
            raise ValueError("arrival_at must be after departure_at")
        if self.source.strip().casefold() == self.destination.strip().casefold():
            raise ValueError("source and destination must differ")
        return self

class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str
    source: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    capacity: int
    available_seats: int
    price: int
    status: str

class BookingCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: EmailStr
    service_id: int = Field(gt=0)
    seats: int = Field(ge=1, le=20)
    passenger_names: list[str] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passengers_match_seats(self):
        if len(self.passenger_names) != self.seats:
            raise ValueError("passenger_names count must equal seats")
        if any(not n.strip() or len(n) > 120 for n in self.passenger_names):
            raise ValueError("passenger names must be non-empty and at most 120 characters")
        return self

class TicketOut(BaseModel):
    ticket_code: str
    passenger_name: str
    status: str
    signature: str

class BookingOut(BaseModel):
    reference: str
    customer_name: str
    customer_email: str
    service_id: int
    seats: int
    total_price: int
    status: str
    created_at: datetime
    tickets: list[TicketOut]

class CancelOut(BaseModel):
    reference: str
    status: str
    seats_released: int

class ValidateTicketIn(BaseModel):
    ticket_code: str = Field(min_length=8, max_length=48)
    signature: str = Field(min_length=64, max_length=64)

class TicketValidationOut(BaseModel):
    valid: bool
    status: str
    message: str
    ticket_code: str

class AnalyticsOut(BaseModel):
    total_bookings: int
    active_bookings: int
    tickets_sold: int
    revenue_gc: int
    occupancy_percent: float
    average_booking_size: float
    single_bookings: int
    group_bookings: int
    cancelled_bookings: int
    completed_bookings: int
    bookings_by_category: dict[str, int]
    revenue_by_category: dict[str, int]
