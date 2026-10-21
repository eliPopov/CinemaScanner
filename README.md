Cinema Finder

An application for finding movie screenings near a location in Israel.

The planned user flow is:

The user enters a location and date.

The app finds nearby cinemas and their screenings.

Results are normalized across cinema chains and sorted by screening time.

The user opens a screening to view seat availability and central-seat recommendations.

The supported cinema chains are planned to be:

Cinema City

Hot Cinema

Yes Planet

Lev Cinema

Movieland

Project structure

cinema-finder/
├── backend/ FastAPI service and cinema adapters
├── frontend/ React + TypeScript application (planned)
├── README.md
└── .gitignore

Backend

The backend uses Python, FastAPI, and Pydantic. It contains normalized cinema,
movie, screening, and seat models, live provider adapters, and a static cinema
catalog used in place of a database for the MVP.

Run locally

PowerShell, from the repository root (no activation required):

```powershell
cd backend
# First-time setup only: python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Use the virtual environment's Python explicitly so Uvicorn uses the project's
dependencies, including `tzdata`, required for `Asia/Jerusalem` on Windows.
If a server is already running in the terminal, stop it with Ctrl+C first.

From the repository root:

cd backend
python -m venv .venv
source .venv/Scripts/activate # Git Bash on Windows

# .venv/Scripts/Activate.ps1 # PowerShell

# .venv/Scripts/activate.bat # Command Prompt

pip install -e ".[dev]"
uvicorn app.main:app --reload

The API will be available at:

http://localhost:8000

Interactive API docs: http://localhost:8000/docs

Current endpoints:

GET /health

GET /api/cinemas

GET /api/cinemas?chain=cinema_city

GET /api/screenings?date=YYYY-MM-DD

GET /api/screenings/{screening_id}/seats

GET /api/search?date=YYYY-MM-DD&latitude=...&longitude=...&radius_km=35

Use today's date or a date with published screenings. Historical dates can return
an empty list because schedules are fetched live and are not archived.
`/api/cinemas` returns the static branch catalog: 8 Cinema City, 6 Planet, 12
Hot Cinema, 6 Movieland, and 7 Lev locations. Each cinema includes
`schedule_supported` and `seats_supported`. Schedules are enabled for Planet,
Hot Cinema, Movieland, and Lev branches. Cinema City's public schedule API
changed in October 2026, so its branch catalog and Glilot seat lookup remain
available while its replacement schedule API is being normalized. Use
`chain=...` or `cinema_id=...` to limit a request.

Nearby search

`GET /api/search` finds catalog cinemas within a straight-line radius of the
supplied WGS84 coordinates. `radius_km` defaults to 35 km and accepts values
above 0 through 100 km. It returns cinemas ordered by distance, their current
screenings, and a seat-count summary for each screening when the provider makes
one available. A `seat_status` of `unsupported` or `unavailable` means the
screening is still returned but no seat count could be obtained.

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/search?date=$screeningDate&latitude=32.0853&longitude=34.7818&radius_km=35"
```

PowerShell example with the server running:

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=yes-planet-ayalon"
```

Development status

FastAPI project structure

Normalized cinema, movie, screening, and seat models

Cinema registry and initial API routes

Cinema City schedule adapter (awaiting its replacement public schedule API)

Yes Planet schedule adapter

Hot Cinema schedule and session adapter

Lev Cinema adapter

Movieland schedule and session adapter

PostgreSQL persistence

React frontend

Seat retrieval

On-demand seat retrieval is implemented for all five adapters. A live check on
2026-10-21 confirmed Lev Tel Aviv layout and status retrieval after anonymous
session initialization; its booking-site IDs 5 through 10 map to that branch.
Movieland uses the temporary-session adapter shared with Hot Cinema.

Seat results include layout, availability, section IDs, seat kinds, status counts,
and a retrieval timestamp. Unavailable seats are not automatically counted as
occupied. No seats are selected or held. See backend/README.md for API details.
Location/radius search, occupancy calculations, and central-seat recommendations
remain pending. PostgreSQL is optional for the MVP; the static catalog is the
current source of cinema data.
