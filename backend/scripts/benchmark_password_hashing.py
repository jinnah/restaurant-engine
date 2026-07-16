"""Benchmark Argon2id verification on this machine (ADR-010).

Acceptance criterion: password verification should take 100-500 ms on the
production VPS. Run this on the deployment target (Milestone 8 runbook) and
whenever the parameters in ``app.core.security`` change::

    uv run --directory backend python -m scripts.benchmark_password_hashing

Out-of-window results trigger a parameter-change ADR — never an ad-hoc
constant edit.
"""

import statistics
import time

from app.core.security import (
    ARGON2_MEMORY_COST_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    hash_password,
    verify_password,
)

_ROUNDS = 10
_TARGET_WINDOW_MS = (100, 500)


def main() -> None:
    sample_password = "benchmark-only-sample-password"  # noqa: S105 - not a credential
    password_hash = hash_password(sample_password)

    durations_ms: list[float] = []
    for _ in range(_ROUNDS):
        started = time.perf_counter()
        assert verify_password(password_hash, sample_password)  # noqa: S101
        durations_ms.append((time.perf_counter() - started) * 1000)

    median = statistics.median(durations_ms)
    low, high = _TARGET_WINDOW_MS
    verdict = "WITHIN" if low <= median <= high else "OUTSIDE"
    print(  # noqa: T201 - this script's entire purpose is console output
        f"argon2id t={ARGON2_TIME_COST} m={ARGON2_MEMORY_COST_KIB}KiB "
        f"p={ARGON2_PARALLELISM}: median verify {median:.0f} ms over "
        f"{_ROUNDS} rounds ({min(durations_ms):.0f}-{max(durations_ms):.0f} ms) "
        f"-- {verdict} the {low}-{high} ms acceptance window (ADR-010)"
    )


if __name__ == "__main__":
    main()
