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
- `GET /api/screenings?date=2026-09-08`

Schedule adapters are intentionally registered incrementally. Until an adapter
is implemented, that chain returns no screenings rather than fabricated data.
