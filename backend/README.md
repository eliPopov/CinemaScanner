# Cinema Finder backend

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

The API is then available at `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

Current endpoints:

- `GET /health`
- `GET /api/cinemas`
- `GET /api/cinemas?chain=cinema_city`
- `GET /api/screenings?date=YYYY-MM-DD`

Schedule adapters are intentionally registered incrementally. Until an adapter
is implemented, that chain returns no screenings rather than fabricated data.

Cinema City schedules are live for the configured Glilot branch:

```text
GET /api/screenings?date=YYYY-MM-DD&chain=cinema_city
GET /api/screenings?date=YYYY-MM-DD&cinema_id=cinema-city-glilot
```

Replace `YYYY-MM-DD` with today's date or a date with published screenings.
For example, in PowerShell with the server running locally:

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=cinema-city-glilot"
```

An empty JSON list (`[]`) means no matching screenings were returned. Historical
dates can return no events: this service fetches the current provider schedule
and does not archive past screenings. Unknown cinema IDs and chains without an
implemented adapter also return an empty list. Use `/api/cinemas` to find valid IDs;
currently `cinema-city-glilot` and `yes-planet-ayalon` have live schedule adapters.

The adapter fetches `/tickets/Movies`, then `/tickets/Events` for each movie
using `MovieId` and a `dd/mm/yyyy` date, with at most four requests in flight.
It parses the nested `Dates` arrays, filters by `TheaterId` and calendar date,
deduplicates events, and returns times in `Asia/Jerusalem` (including DST).
Unknown metadata remains null; seat lookup still returns 501. Provider HTTP,
timeout, JSON, or schema failures return 502 instead of an empty or partial schedule.
Schedules are fetched afresh on each request; no cache or database is required.

The old Cinema City Ayalon entry was a placeholder with no matching provider
branch. It has been replaced by Glilot, using `TixTheatreId=1170` from the
provider's public theater directory. To add a branch, add its cinema configuration
and its verified `TixTheatreId` mapping in `app/adapters/cinema_city.py`.
The directory and response structure were checked on 2026-09-08 at
`https://www.cinema-city.co.il/` and
`https://www.cinema-city.co.il/tickets/Theaters?MovieId=6123&Date=08/09/2026`.

Run offline tests with `python -m pytest -q`. Adapter and endpoint tests use
`httpx.MockTransport` and never contact cinema sites. Install the declared
`tzdata` dependency for timezone support on Windows.

## Yes Planet schedules

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=yes-planet-ayalon"
```

You can also filter with `chain=yes_planet`. With no chain or cinema filter,
the endpoint combines Cinema City and Planet results sorted by start time.

`app/adapters/yes_planet.py` uses Planet's public schedule endpoint:

```text
https://www.planetcinema.co.il/il/data-api-service/v1/quickbook/10100/film-events/in-cinema/{cinema_id}/at-date/{YYYY-MM-DD}
```

Ayalon's provider ID is `1025`, verified in `apiSitesList` on
`https://www.planetcinema.co.il/` on 2026-09-13. Each request reads the requested
and previous business days so after-midnight screenings can be filtered to the
requested Israel calendar date. Duplicate events are removed. Times include
the `Asia/Jerusalem` UTC offset. Movie titles, posters, trailers, and booking
URLs come from the provider; no booking or seat endpoints are called.

Language and subtitle values use provider language codes (such as `he` and `en`),
joined with commas when multiple languages are present. Dubbed or voiceover
language takes precedence over original language. Recognized format attributes
are normalized to display labels; unknown metadata remains null. Missing required
fields, broken film references, HTTP errors, and timeouts produce 502, including
when only one of the two business-day requests fails. Seat lookup remains 501.

## Schedule security

Both adapters reject HTTP redirects rather than following them. The configured
schedule endpoints were checked to return JSON directly. If a provider changes
its endpoint, verify the new HTTPS address before updating the adapter.

Planet booking links must use HTTPS on the exact verified host
`tickets5.planetcinema.co.il`, standard port 443, and contain no embedded credentials.
Other links produce 502. When adding branches, verify any additional booking
hosts before extending `BOOKING_HOSTS`; do not allow arbitrary subdomains.

Before public deployment, add a bounded schedule cache with a short expiry,
coalesce simultaneous requests for the same cinema/date into one fetch, and add
provider-wide concurrency limits, an overall fetch deadline, and API rate limits.
The current Cinema City concurrency limit applies to each individual API request.
