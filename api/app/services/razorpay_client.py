"""Thin wrapper over the Razorpay Orders API (docs/03-payment-integration.md).

No real Razorpay account/credentials exist for this build — RAZORPAY_KEY_ID
and RAZORPAY_KEY_SECRET are empty by default (app/config.py).
get_razorpay_client() refuses to construct a client without them rather
than silently doing nothing; tests substitute a fake client via FastAPI's
dependency_overrides (app/routers/payments.py), which never affects
production wiring.
"""

import httpx

from app.config import settings


class RazorpayClient:
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self.key_secret = key_secret

    async def create_order(self, *, amount_paise: int, currency: str = "INR", receipt: str | None = None) -> dict:
        async with httpx.AsyncClient(
            base_url=self.BASE_URL, auth=(self.key_id, self.key_secret), timeout=10.0
        ) as client:
            resp = await client.post(
                "/orders", json={"amount": amount_paise, "currency": currency, "receipt": receipt}
            )
            resp.raise_for_status()
            return resp.json()


def get_razorpay_client() -> RazorpayClient:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError(
            "Razorpay credentials are not configured (RAZORPAY_KEY_ID / "
            "RAZORPAY_KEY_SECRET). Set test-mode keys before calling "
            "POST /payments/intent."
        )
    return RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
