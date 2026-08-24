"""
Internal API key auth for billing service endpoints.
The Telegram bot passes BILLING_SECRET_KEY in headers.
"""
import hmac
import os
from fastapi import Header, HTTPException, status

BILLING_SECRET_KEY = os.environ.get("BILLING_SECRET_KEY", "")

if not BILLING_SECRET_KEY:
    # Fail loudly at import time rather than silently disabling auth at
    # request time. A missing key in production must never mean "open API".
    raise RuntimeError(
        "BILLING_SECRET_KEY is not set. Refusing to start with internal "
        "API auth disabled — set it in .env (any long random string)."
    )


def verify_internal_key(x_billing_key: str = Header(..., alias="X-Billing-Key")):
    if not hmac.compare_digest(x_billing_key, BILLING_SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )
