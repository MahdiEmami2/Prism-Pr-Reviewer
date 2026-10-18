"""DEMONSTRATION DATA — placeholder-only configuration.

This file exists to prove the placeholder safeguard: PRISM must not report a hard-coded
credential for any value below, because every one of them is recognisably a placeholder or
an environment lookup rather than a real secret.

Do not put real values in this file.
"""

import os

# Environment lookups are correct and must never be flagged.
DATABASE_PASSWORD = os.environ.get("SAMPLE_DATABASE_PASSWORD")
SERVICE_API_KEY = os.getenv("SAMPLE_SERVICE_API_KEY")

# Obvious placeholders must never be flagged.
PLACEHOLDER_PASSWORD = "changeme"
PLACEHOLDER_TOKEN = "your_token_here"
PLACEHOLDER_SECRET = "<inject-at-deploy-time>"
PLACEHOLDER_API_KEY = "${SAMPLE_API_KEY}"
PLACEHOLDER_ACCESS_KEY = "0000000000"
PLACEHOLDER_AUTH_TOKEN = "example-token"
PLACEHOLDER_CONNECTION_STRING = ""

REQUEST_TIMEOUT_SECONDS = 10.0
TLS_VERIFY = True
