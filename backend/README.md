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
currently `cinema-city-glilot`, `yes-planet-ayalon`, `hot-cinema-petah-tikva`, `lev-tel-aviv`, and `movieland-karmiel`
have live schedule adapters.

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
the endpoint combines all implemented providers' results sorted by start time.

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

Schedule adapters reject HTTP redirects rather than following them. The configured
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

## Hot Cinema schedules and temporary sessions

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=hot-cinema-petah-tikva"
```

The adapter makes one anonymous GET to
`https://www.hotcinema.co.il/tickets/TheaterEvents2?theatreid=14&date=dd/mm/yyyy`.
It parses `TheaterEvents[].Dates`, filters by cinema and Israel calendar date,
deduplicates and sorts screenings. Language labels come directly from the provider;
unknown original language and format remain null. Booking links use the fixed
Hot Cinema `/order` URL. Theater ID 14 and Bigger Picture site ID 1194 were verified
from `/theater/14` and its booking link on 2026-09-13.

Schedules never create sessions. Backend code can use the separate helper:

```python
async with adapter.open_session(cinema=cinema) as session:
    events = await session.get_event(event_code)  # schedule EventId
    if events:
        statuses = await session.get_seat_status(events[0]["ei"])  # internal event ID
```

Use one context per operation and await reads sequentially. The helper lazily
creates an anonymous session via POST `/sys/login` at the fixed origin
`https://pub-api-use1.biggerpicture.ai/ecomAPI/public/api`. Tokens stay in memory,
are masked in representations, and are discarded on close. Reads retry once with
a new session after 401. Redirects are rejected and event IDs must be numeric.
Only explicit event/status GET methods are exposed. No carts, seat selections,
holds, or purchases are performed. Playwright is not required.

Session errors raise `HotCinemaSessionError`; schedule errors become HTTP 502.
The public seats endpoint remains 501 until SeatMap normalization is implemented.
An empty raw status response does not establish seat availability or occupancy.

## Lev schedules

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=lev-tel-aviv"
```

Lev's public schedule uses GET `/wp-content/themes/lev/ajax_data.php` on
`https://www.lev.co.il`, with `clang=he`, `action=movie_on_location_new`,
`loc=לב תל אביב`, and an ISO date. The branch name matches the site's
`locationfilter1` options; legacy numeric location IDs are not used.

The response is HTML. Beautiful Soup parses visible screening rows and ignores
commented-out duplicates. Times are combined with the requested calendar date
in `Asia/Jerusalem`: the response does not independently include a full date or
branch name, so those filters rely on the provider. Movie-page paths provide
stable movie identifiers; unknown metadata remains null. Booking URLs must match
the verified Lev HTTPS origin and the row's numeric `pcode` and `loc` values.
The booking `loc` value is preserved per row, not treated as the branch filter.

Only the provider's recognized no-schedule notice becomes an empty list; blank,
malformed, or unexpected HTML returns 502. Redirects are rejected. No sessions or
booking pages are opened. Seat lookup remains 501. The live check on 2026-09-13
returned 22 Tel Aviv screenings; counts change over time.

## Movieland schedules

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=movieland-karmiel"
```

The adapter fetches `https://movieland.co.il/api/Events` with `TheatreId=1290`
(note the spelling) and `Date=dd/mm/yyyy`. Karmiel's `TixTheatreId` was verified
in the public branch selector on 2026-09-13. The canonical host has no `www`;
the adapter rejects redirects. No login or session is needed for schedules.

Movie groups contain `Dates` with event/movie/theater IDs and ISO timestamps.
The adapter filters cinema and Israel calendar date, verifies movie IDs, removes
duplicates, and sorts results. Booking links use the site's `/order/` pattern
with `eventID`, `MovieId`, and `theaterId`; upstream `BookingNativeUrl` is not used.
Explicit `ThreeD`, `IsVip`, and `HebrewSubs` flags supply format/subtitle metadata.
A dubbing flag alone does not identify a language, so spoken language stays null.
Unknown poster paths and other metadata are not guessed. Failures return 502.
Seat/session integration is deferred; the public seats endpoint remains 501.
The live check on 2026-09-13 returned 31 Karmiel screenings.
