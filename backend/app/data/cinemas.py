from app.models.cinema import Cinema

# This is deliberately configuration for now. It can later be replaced by a
# repository backed by PostgreSQL without changing the API routes.
CINEMAS: list[Cinema] = [
    Cinema(
        id="cinema-city-glilot",
        chain="cinema_city",
        name="Cinema City Glilot",
        address="Rav Mecher Building, Glilot Junction, Ramat Hasharon",
        latitude=32.146436,
        longitude=34.802543,
    ),
    Cinema(
        id="yes-planet-ayalon",
        chain="yes_planet",
        name="Planet Ayalon",
        address="Ayalon Mall, Ramat Gan",
        latitude=32.1011,
        longitude=34.8242,
    ),
    Cinema(
        id="hot-cinema-petah-tikva",
        chain="hot_cinema",
        name="Hot Cinema Petah Tikva",
        address="Petah Tikva",
        latitude=32.0879,
        longitude=34.8878,
    ),
    Cinema(
        id="lev-tel-aviv",
        chain="lev",
        name="Lev Tel Aviv",
        address="Dizengoff 50, Tel Aviv",
        latitude=32.0753,
        longitude=34.7748,
    ),
    Cinema(
        id="movieland-karmiel",
        chain="movieland",
        name="Movieland Karmiel",
        address="Karmiel",
        latitude=32.9199,
        longitude=35.2985,
    ),
]
