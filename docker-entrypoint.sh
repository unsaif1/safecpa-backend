#!/usr/bin/env bash
set -euo pipefail

SECRETS_DIR="/run/secrets"
SECRETS_FILE="${SECRETS_DIR}/safecpa.env"
RUNTIME_FILE="/app/.env"

# Expose decrypted secrets to the app process
if [ -f "$SECRETS_FILE" ]; then
  cp "$SECRETS_FILE" "$RUNTIME_FILE"
  chmod 600 "$RUNTIME_FILE"
else
  echo "WARNING: No secrets file found at $SECRETS_FILE. App may fail."
fi

exec "$@"
