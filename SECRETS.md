# SaifHaven Backend — Secrets Management

## Directory layout

```
backend/
├── secrets/
│   ├── safecpa.env.enc      ← GPG-encrypted, safe to commit
│   └── safecpa.env           ← plaintext, NEVER commit (mode 600)
├── docker-compose.yml        ← uses secrets/ mount
└── docker-entrypoint.sh      ← decrypts and injects at container start
```

## Secrets in the repo

`secrets/safecpa.env.enc` is **encrypted with GPG** and safe to push.  
`secrets/safecpa.env` is the **decrypted working copy** — it is `.gitignore`-d.

The GPG key is **localhost-only** (`tony@hermes-agent.local`, key ID `ACBF1F227ED99643`).  
Regenerate per-environment if you need cross-host keying.

## Rotation procedure

### 1. Edit current secrets

```bash
gpg --batch --decrypt \
    /root/hermes-safecpa-backend/secrets/safecpa.env.enc \
    | sed 's/^password:.*/password: YOUR_NEW_PASSWORD/' \
    | gpg --batch --yes --encrypt --recipient ACBF1F227ED99643 \
          --output /root/hermes-safecpa-backend/secrets/safecpa.env.enc \
          --armor -
```

For full edits, decrypt to a temp file, edit, then re-encrypt:

```bash
gpg --batch --decrypt secrets/safecpa.env.enc > /tmp/safecpa_plain.env
# → edit /tmp/safecpa_plain.env with your values
gpg --batch --yes --encrypt --recipient ACBF1F227ED99643 \
    --output secrets/safecpa.env.enc --armor /tmp/safecpa_plain.env
chmod 600 /tmp/safecpa_plain.env
rm    /tmp/safecpa_plain.env
```

### 2. Deploy to container

```bash
# decrypt to runtime secrets path
gpg --batch --decrypt secrets/safecpa.env.enc > /run/secrets/safecpa.env
chmod 600 /run/secrets/safecpa.env
docker-compose up -d
```

Or use the entrypoint helper:

```bash
docker-compose run --rm api /app/docker-entrypoint.sh
```

### 3. Verify

```bash
docker-compose exec api env | grep -E 'OPENROUTER|SMTP_'
```

No plaintext `.env` files should exist inside the container image.

## Production notes

- For production, swap Docker secrets for a vault (1Password, Doppler, Infisical).
- Rotate `OPENROUTER_API_KEY` after every session where it appeared in plaintext.
- Set `SMTP_HOST/PORT/USER/PASS/FROM/TO` only if you need `/api/contact`; otherwise leave all empty to disable the route (503: SMTP not configured).
