from pydantic import BaseModel, Field


class Cinema(BaseModel):
    id: str
    chain: str
    name: str
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    schedule_supported: bool = False
    seats_supported: bool = False


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

