from fastapi import FastAPI

from app.routes import cinemas, health, screenings

app = FastAPI(
    title="CinemaScanner API",
    version="0.1.0",
    description="Search Israeli cinema screenings and inspect seat availability.",
)

app.include_router(health.router)
app.include_router(cinemas.router, prefix="/api")
app.include_router(screenings.router, prefix="/api")

