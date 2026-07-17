"""Login backoff policy (M2A, ADR-010).

Per-account exponential backoff instead of a hard lockout: an attacker is
capped at roughly one guess per minute per account, while a legitimate
owner under active attack waits at most ``BACKOFF_CAP_SECONDS`` — never
hours. Responses are uniform 401s regardless of throttle state; attempts
inside the window never touch the counter (extending the window would
recreate the lockout denial-of-service this design removed).

Atomic counters prevent lost updates, but this is deliberately **not** a
strict global rate limit (ADR-010): per-IP/per-connection limiting at the
reverse proxy is a mandatory Milestone 8 item before production.
"""

from datetime import UTC, datetime, timedelta

BACKOFF_THRESHOLD = 5  # consecutive failures before backoff engages
BACKOFF_CAP_SECONDS = 60


def required_backoff_seconds(failed_login_count: int) -> int:
    """Minimum seconds required since the last failure before a real attempt.

    0 while under the threshold; then 1, 2, 4, ... capped at 60.
    """
    if failed_login_count < BACKOFF_THRESHOLD:
        return 0
    exponent = failed_login_count - BACKOFF_THRESHOLD
    if exponent >= BACKOFF_CAP_SECONDS.bit_length():
        return BACKOFF_CAP_SECONDS
    return min(1 << exponent, BACKOFF_CAP_SECONDS)


def is_throttled(
    failed_login_count: int,
    last_failed_login_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """True when a login attempt arrives inside the account's backoff window."""
    backoff = required_backoff_seconds(failed_login_count)
    if backoff == 0 or last_failed_login_at is None:
        return False
    moment = now if now is not None else datetime.now(UTC)
    return moment < last_failed_login_at + timedelta(seconds=backoff)
