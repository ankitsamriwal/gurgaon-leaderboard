"""docs/02-api-spec.md: "rera_number format-checked against Haryana RERA
number pattern." No authoritative format is given in the spec docs, and
this build has no access to the real Haryana RERA portal (haryanarera.gov.in)
to confirm one.

This is a best-effort shape check based on the publicly known convention
(RC/REP/HARERA/<zone>/...), NOT a source of truth — docs/05-security-anti-fraud.md
is explicit that only manual admin verification against the real portal
marks rera_verified=true. Confirm the exact pattern with someone who has
current access to real registration numbers before relying on this for
anything beyond "reject obvious garbage input".
"""

import re

RERA_NUMBER_PATTERN = re.compile(r"^RC/REP/HARERA/[A-Z]{2,10}(/[A-Z0-9]+)+$", re.IGNORECASE)


def is_valid_rera_number_format(value: str) -> bool:
    return bool(RERA_NUMBER_PATTERN.match(value.strip()))
