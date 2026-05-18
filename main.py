"""
SaifHaven.com — FastAPI Backend
Endpoints:
  GET  /api/health            – health check
  POST /api/contact           – send contact form via SMTP
  POST /api/chat              – AI chatbot (OpenRouter Hermes)
  GET  /api/nft-metrics       – fake NFT portfolio metrics
"""
import os
import json
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import uvicorn

# ── Secrets loading ──────────────────────────────────────────────────────────
# Priority order: env_file (/.env) → Docker secrets (/run/secrets/safecpa.env) → env vars
def _load_secrets() -> None:
    """Load credential values from Docker secrets or .env file into os.environ."""
    candidates = [
        "/run/secrets/safecpa.env",   # Docker Compose secrets
        "/app/.env",                   # legacy entrypoint copy
        "/app/.env.local",             # local overrides
    ]
    for path in candidates:
        p = Path(path)
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_secrets()

# ── Chat auth key ───────────────────────────────────────────────────────────
CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY", "")

# ── App factory ─────────────────────────────────────────────────────────────
app = FastAPI(title="SaifHaven API", version="1.0.0")

# Public CORS — keep as-is
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _chat_auth_middleware(request: Request, call_next):
    """
    Gate /api/chat behind x-api-key header.
    Other endpoints (health, nft, contact) remain public.
    """
    if request.url.path == "/api/chat":
        if CHATBOT_API_KEY:
            provided_key = request.headers.get("x-api-key")
            if provided_key != CHATBOT_API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "unauthorized — include x-api-key header"},
                )
    return await call_next(request)

# ── Config ──────────────────────────────────────────────────────────────────
APP_PORT   = int(os.getenv("APP_PORT",   "8000"))
APP_HOST   = os.getenv("APP_HOST",   "0.0.0.0")

# SMTP secrets – MUST come from secrets file or env; do NOT hardcode
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@saifhaven.com")
SMTP_TO   = os.getenv("SMTP_TO",   SMTP_FROM)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Log files
LOG_DIR    = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
CHAT_LOG   = LOG_DIR / "conversations.json"
CONTACT_LOG = LOG_DIR / "contacts.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _log_event(path: Path, record: dict) -> None:
    """Append a JSON record to a logfile (one JSON object per line)."""
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


async def _openrouter_chat(messages: list[dict]) -> str:
    if not OPENROUTER_KEY:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":  "nousresearch/hermes-3-llama-3.1-405b:free",
                "messages": messages,
                "max_tokens": 1024,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "saifhaven-api", "ts": datetime.now(timezone.utc).isoformat()}


@app.post("/api/contact")
async def contact(request: Request):
    """
    Receives {name, email, subject, message} from the contact form.
    Sends an email via SMTP. Returns 202 on success.
    """
    body = await request.json()
    name    = body.get("name",    "").strip()
    email   = body.get("email",   "").strip()
    subject = body.get("subject", "New SaifHaven Inquiry").strip()
    message = body.get("message", "").strip()

    if not all([name, email, message]):
        raise HTTPException(status_code=400, detail="name, email, and message are required")

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        raise HTTPException(status_code=503, detail="SMTP not configured on server")

    msg = MIMEMultipart("alternative")
    msg["From"]    = SMTP_FROM
    msg["To"]      = SMTP_TO
    msg["Subject"] = f"[SaifHaven] {subject}"

    text_part = MIMEText(
        f"Name:    {name}\nEmail:   {email}\nSubject: {subject}\n\n{message}",
        "plain", "utf-8",
    )
    html_part = MIMEText(
        f"<html><body>"
        f"<h3>SaifHaven — New Inquiry</h3>"
        f"<p><strong>Name:</strong> {name}<br>"
        f"<strong>Email:</strong> {email}<br>"
        f"<strong>Subject:</strong> {subject}</p>"
        f"<p>{message.replace(chr(10), '<br>')}</p>"
        f"</body></html>",
        "html", "utf-8",
    )
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            if SMTP_PORT == 465:
                server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [SMTP_TO], msg.as_string())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SMTP error: {exc}")

    _log_event(CONTACT_LOG, {"name": name, "email": email, "subject": subject, "message": message})

    return {"status": "sent", "message": "Inquiry received. We'll be in touch shortly."}


@app.post("/api/chat")
async def chat(request: Request):
    """
    AI chatbot powered by OpenRouter (Hermes model).
    Persists conversation to logs/conversations.json.
    Body: { session_id?, message }
    """
    body    = await request.json()
    message = body.get("message", "").strip()
    sid     = body.get("session_id") or str(uuid.uuid4())

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Load existing history for this session
    session_file = LOG_DIR / f"chat-{sid}.json"
    history = []
    if session_file.exists():
        with session_file.open() as f:
            history = json.load(f)

    # Append user message
    history.append({"role": "user", "content": message, "ts": datetime.now(timezone.utc).isoformat()})

    # Build context (keep last 30 turns to stay within token budget)
    recent = history[-30:]
    system_prompt = (
        "You are Saif, the helpful AI assistant for SaifHaven.com — an AI tech solutions company. "
        "SaifHaven provides: website health checks, AI chatbot integrations, full-stack builds, "
        "marketing automation, and CRM integrations for businesses. "
        "Be concise, professional, and friendly. "
        "When the user seems ready to buy or needs a custom quote, "
        "invite them to reach out via the contact form at #contact or email hello@saifhaven.com. "
        "Never pretend to know personal data you were not given."
    )

    try:
        reply = await _openrouter_chat(
            [{"role": "system", "content": system_prompt}] + recent
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    history.append({"role": "assistant", "content": reply, "ts": datetime.now(timezone.utc).isoformat()})

    # Persist
    with session_file.open("w") as f:
        json.dump(history, f, indent=2)
    _log_event(CHAT_LOG, {"session_id": sid, "role": "assistant", "content": reply})

    return {
        "session_id": sid,
        "reply": reply,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/nft-metrics")
def nft_metrics():
    """
    Returns static (but structured) NFT / portfolio metrics for the homepage.
    Real data hook: replace the dict below with a live chain/NFT API call.
    """
    return {
        "portfolio": {
            "total_items":  42,
            "floor_value_eth": "4.2",
            "floor_value_usd": "7,560",
            "traits_rarity_avg": 92.4,
        },
        "overview": {
            "total_volume_eth": "126.0",
            "owner_address":    "0xSaif…Haven",
            "network":          "Ethereum",
            "last_updated":     datetime.now(timezone.utc).isoformat(),
        },
        "performance": {
            "best_sale_eth": "12.5",
            "avg_sale_eth":  "3.0",
            "listings_active": 3,
        },
    }


@app.get("/api/nft-collection")
def nft_collection():
    """Extended collection data — feeds the NFT showcase section."""
    return {
        "collection": "SaifHaven Genesis",
        "items": [
            {"id": 1, "name": "The Consigliere",   "trait": "Wisdom",   "rarity": "Legendary",  "value_eth": 8.1,  "thumbnail": "nft-1.png"},
            {"id": 2, "name": "Road Warrior",      "trait": "Grit",      "rarity": "Epic",       "value_eth": 5.4,  "thumbnail": "nft-2.png"},
            {"id": 3, "name": "Code Architect",    "trait": "Precision", "rarity": "Rare",       "value_eth": 3.2,  "thumbnail": "nft-3.png"},
            {"id": 4, "name": "Night Owl",         "trait": "Stealth",   "rarity": "Uncommon",   "value_eth": 2.1,  "thumbnail": "nft-4.png"},
            {"id": 5, "name": "Stacker",           "trait": "Power",     "rarity": "Common",     "value_eth": 1.0,  "thumbnail": "nft-5.png"},
        ],
    }


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
