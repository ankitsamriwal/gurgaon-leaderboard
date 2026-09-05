import logging

from app.config import settings

logger = logging.getLogger("otp")


class OtpProvider:
    async def send(self, *, phone: str | None, email: str | None, otp: str) -> None:
        raise NotImplementedError


class LogOtpProvider(OtpProvider):
    """Dev/test stand-in — logs the code instead of sending a real SMS/email.

    docs/00-overview.md names MSG91/Twilio as the real provider; wiring one
    up is not yet done (no real account/credentials exist for this build).
    get_otp_provider() below refuses to fall back to this in production.
    """

    async def send(self, *, phone: str | None, email: str | None, otp: str) -> None:
        logger.info("OTP for %s: %s", phone or email, otp)


def get_otp_provider() -> OtpProvider:
    if settings.is_production:
        raise RuntimeError(
            "No production OTP provider configured. Wire up a real SMS/email "
            "provider (MSG91/Twilio, per docs/00-overview.md) before this "
            "can run with ENVIRONMENT=production."
        )
    return LogOtpProvider()
