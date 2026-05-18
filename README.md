# safecpa-backend — SaifHaven FastAPI Backend

Lightweight FastAPI backend powering SaifHaven.com: contact form, AI chatbot (OpenRouter Hermes), and NFT portfolio endpoints.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/contact` | Contact form (SMTP) |
| POST | `/api/chat` | AI chatbot (OpenRouter Hermes) |
| GET | `/api/nft-metrics` | Static NFT portfolio metrics |
| GET | `/api/nft-collection` | Extended collection data |

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your values
uvicorn main:app --reload     # http://localhost:8000
```

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

## Environment variables

See `.env.example` for a full list. Required:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` — contact form email
- `OPENROUTER_API_KEY` — chatbot OpenRouter API key
- `APP_PORT` (default `8000`), `APP_HOST` (default `0.0.0.0`) — server bind

## Running tests

```bash
pytest -v
```

Requires the packages in `requirements.txt`. SMTP is mocked in tests; no real emails are sent.

## Architecture notes

- CORS is set to `allow_origins=["*"]` — tighten for production.
- Chat history persists to `logs/` as per-session JSON files.
- Chat model is `nousresearch/hermes-3-llama-3.1-405b:free` on OpenRouter.
- No auth middleware on backend yet — frontend `x-api-key` check is the primary guard.

