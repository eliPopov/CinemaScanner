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

The backend uses Python, FastAPI, and Pydantic. It currently contains the API
structure, normalized models, and the cinema registry. Cinema-specific schedule
and seat adapters are being implemented incrementally.

Run locally

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

Use today's date or a date with published screenings. Historical dates can return
an empty list because schedules are fetched live and are not archived.
Live schedule adapters support `cinema-city-glilot`, `yes-planet-ayalon`, and
`hot-cinema-petah-tikva`, `lev-tel-aviv`, and `movieland-karmiel`. Use `chain=cinema_city`,
`chain=yes_planet`, `chain=hot_cinema`, `chain=lev`, or `chain=movieland` to filter by chain,
or omit the filter to combine schedules.

PowerShell example with the server running:

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=cinema-city-glilot"
```

Development status

FastAPI project structure

Normalized cinema, movie, screening, and seat models

Cinema registry and initial API routes

Cinema City schedule adapter

Yes Planet schedule adapter

Hot Cinema schedule and session adapter

Lev Cinema adapter

Movieland schedule and session adapter

PostgreSQL persistence

React frontend
