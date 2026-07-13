"""
Internal API key auth for billing service endpoints.
The Telegram bot passes BILLING_SECRET_KEY in headers.
"""
import os
from fastapi import Header, HTTPException, status

BILLING_SECRET_KEY = os.environ.get("BILLING_SECRET_KEY", "")


def verify_internal_key(x_billing_key: str = Header(..., alias="X-Billing-Key")):
    if not BILLING_SECRET_KEY:
        return  # disabled in dev
    if x_billing_key != BILLING_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )
