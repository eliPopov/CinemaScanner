# Cinema Finder backend

## Run locally

In PowerShell, from `backend/`, use the virtual environment directly:

```powershell
# First-time setup only: python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

This avoids accidentally launching a globally installed Uvicorn. If startup fails
with `No module named 'tzdata'` or `No time zone found with key Asia/Jerusalem`,
stop the existing server with Ctrl+C and use these commands. `tzdata` is already
a declared project dependency; install and launch with the same Python.

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
- `GET /api/search?date=YYYY-MM-DD&latitude=...&longitude=...&radius_km=35`

`app/data/cinema_catalog.py` is the MVP source of cinema data instead of a
database. It currently lists 39 public branches: 8 Cinema City, 6 Planet, 12
Hot Cinema, 6 Movieland, and 7 Lev. Each API cinema record states whether
schedule and seat retrieval are currently supported.

Planet, Hot Cinema, Movieland, and Lev schedules are enabled for every listed
branch. Cinema City changed its public schedule platform in October 2026;
Cinema City branches remain in the catalog and Glilot seat lookup remains
available, but schedule fetching is disabled until the replacement API is
normalized.

## Nearby cinema search

`GET /api/search` filters the static catalog by great-circle distance from the
provided WGS84 `latitude` and `longitude`, using the Haversine formula. The
default `radius_km` is 35; valid values are greater than 0 and no more than 100.
Results are ordered nearest first and grouped by cinema. Each screening includes
`seat_status` plus `seat_availability` counts when its provider supports and
returns a seat map. Schedule and seat-provider failures are reported on the
affected cinema or screening so one unavailable provider does not discard other
nearby results.

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/search?date=$screeningDate&latitude=32.0853&longitude=34.7818&radius_km=35"
```

Replace `YYYY-MM-DD` with today's date or a date with published screenings.
For example, in PowerShell with the server running locally:

```powershell
$screeningDate = Get-Date -Format 'yyyy-MM-dd'
Invoke-RestMethod "http://localhost:8000/api/screenings?date=$screeningDate&cinema_id=yes-planet-ayalon"
```

An empty JSON list (`[]`) means no matching screenings were returned. Historical
dates can return no events: this service fetches the current provider schedule
and does not archive past screenings. Unknown cinema IDs, cinemas with disabled
schedule support, and chains without an implemented adapter also return an empty
list. Use `/api/cinemas` to find valid IDs and capability fields.

The former Cinema City adapter remains covered by offline tests and Glilot's
legacy provider ID remains configured for seat IDs. Its former schedule
endpoints no longer serve the public site, so the API deliberately does not
call them. Schedules are fetched afresh for supported branches; no cache or
database is required.

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
when only one of the two business-day requests fails. Seat lookup is described below.

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
The public seats endpoint now normalizes the event layout and separate status feed.
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
booking pages are opened. Seat lookup is described below. The live check on 2026-09-13
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
Seat/session integration now uses the shared Bigger Picture implementation below.
The live check on 2026-09-13 returned 31 Karmiel screenings.

## On-demand seat maps

```text
GET /api/screenings/{screening_id}/seats
```

Use the exact `id` from a schedule result. No date parameter, database, or prior
request to the same server process is required. Only configured branches are
accepted. The response contains `screening_id`, `total`, `available`, `occupied`,
`held`, `unavailable`, `unknown`, `fetched_at`, and `seats`. Each seat includes
`id`, `section_id`, `row`, `number`, `x`, `y`, `kind`, and `status`.

- 200: complete normalized layout and current provider status.
- 404: unrecognized ID/branch or provider-reported missing screening.
- 502: failed, malformed, unsupported, or timed-out provider retrieval.

Requests have a 60-second overall deadline. Seat results are not cached. Schedule
fetching never initializes these sessions or calls seat endpoints. Only read-only
requests and temporary anonymous session initialization are used; booking page
JavaScript is never executed, and no carts, seat holds, or purchases are created.

### Provider semantics

Cinema City, Planet, and Lev share `presglobal_seats.py`. GET `/order/{id}` supplies
an anonymous UUID cookie/header; GET `/api/presentations/{id}` supplies the venue,
seat-plan ID, and actual venue type. POST `/api/seats/seatplanV2` reads the layout;
GET `/api/seats/seats-statusV2` reads availability. POST here is a read operation.
Origins are fixed to `tickets.cinema-city.co.il`, `tickets5.planetcinema.co.il`, and
`ticket.lev.co.il`. Redirects are rejected and session data is never returned.

PresGlobal status dictionary keys are AVAILABLE seat IDs, including values of 0.
Missing keys mean unavailable; the feed does not distinguish sold, held, and
blocked seats. Thus `occupied=0` means no explicitly reported sold seats, not zero
actual occupancy. Do not calculate occupancy as `1 - available / total`.
Coordinates include provider group translations and rotations.

Hot Cinema and Movieland share `bigger_picture_session.py` (site IDs 1194 and 1290).
The old HotCinemaSession imports remain compatible. Both adapters expose
`open_session(cinema=...)`. Event details contain the seat layout; `seatsStatus`
contains sparse sold/held records. Deleted cells are excluded. A valid empty
status list means no reported sold/held seats only in conjunction with a valid
layout. Coordinates are in provider grid units, local to `section_id`; they are
not geographic coordinates. Unrecognized seat kinds are `other`.

### Verification and remaining limitation

Live read checks on 2026-09-14 returned layouts for Cinema City (33 seats), Planet
(394), Hot Cinema (82), and Movieland (85), one screening per configured branch.
Counts and availability change. Lev's booking-site ID varies by screening (the
Tel Aviv schedule currently returns IDs 5 through 10), so all of those IDs map
to the configured Tel Aviv cinema. A live check on 2026-10-21 confirmed that
Lev returns both a layout and seat status after anonymous-session initialization.

Shared protocol behavior was verified against the providers' booking JavaScript:
Cinema City and Lev's `/order/{id}` pages, Planet's ticket host, and Bigger
Picture's `main.c82d55f06da9ea94.js` as served by Hot Cinema/Movieland. No tokens,
cookies, or booking-page snapshots are stored in this repository.

Tests use mocked HTTP and cover read-only request sequences, normalization,
unknown IDs, malformed/mismatched payloads, redirects, failures, and the shared
session's existing renewal/cleanup tests. Seat-pair recommendations and occupancy
percentages are not implemented by this retrieval change.
