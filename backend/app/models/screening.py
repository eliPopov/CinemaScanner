from datetime import datetime
from pydantic import BaseModel


class Movie(BaseModel):
    id: str
    title: str
    original_title: str | None = None
    rating: float | None = None
    poster_url: str | None = None
    trailer_url: str | None = None


class Screening(BaseModel):
    id: str
    chain: str
    cinema_id: str
    cinema_name: str
    movie: Movie
    starts_at: datetime
    language: str | None = None
    subtitles: str | None = None
    format: str | None = None
    booking_url: str

