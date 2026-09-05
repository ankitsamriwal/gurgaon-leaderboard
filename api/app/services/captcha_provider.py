"""CAPTCHA on /submit and /auth/otp/request (docs/05-security-anti-fraud.md).

Same honesty-over-pretending pattern as app/services/otp_provider.py: no
real hCaptcha/Turnstile site key exists for this build. NoopCaptchaProvider
passes everything outside production; get_captcha_provider() refuses to
run in production without real credentials rather than silently accepting
unverified submissions.
"""

import httpx

from app.config import settings


class CaptchaProvider:
    async def verify(self, token: str | None) -> bool:
        raise NotImplementedError


class NoopCaptchaProvider(CaptchaProvider):
    """Dev/test stand-in — accepts anything, including no token at all."""

    async def verify(self, token: str | None) -> bool:
        return True


class TurnstileProvider(CaptchaProvider):
    """Cloudflare Turnstile siteverify. Untested against the real API — no
    real site/secret key exists for this build; wire up real credentials
    and confirm this against a live Turnstile widget before production."""

    VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    async def verify(self, token: str | None) -> bool:
        if not token:
            return False
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.VERIFY_URL, data={"secret": self.secret_key, "response": token})
            resp.raise_for_status()
            return bool(resp.json().get("success"))


def get_captcha_provider() -> CaptchaProvider:
    if settings.is_production:
        if not settings.turnstile_secret_key:
            raise RuntimeError(
                "No production CAPTCHA provider configured (TURNSTILE_SECRET_KEY). "
                "docs/05-security-anti-fraud.md requires CAPTCHA on /submit and "
                "/auth/otp/request before production."
            )
        return TurnstileProvider(settings.turnstile_secret_key)
    return NoopCaptchaProvider()
