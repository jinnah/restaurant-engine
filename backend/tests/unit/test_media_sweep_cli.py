"""Sweep CLI argument validation and exit-code contract (M3C, correction 4)."""

import uuid

import pytest

from app.domains.media.sweep import MissingObject, SweepReport, VerifyFinding, VerifyReport
from scripts.sweep_media import (
    _batch_size,
    _print_verify,
    _sweep_exit_code,
    _verify_exit_code,
    main,
)


class TestBatchSizeValidation:
    @pytest.mark.parametrize("value", ["0", "-1", "-1000", "100001", "abc"])
    def test_invalid_batch_sizes_are_rejected(self, value: str) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            _batch_size(value)

    @pytest.mark.parametrize("value", ["1", "200", "100000"])
    def test_valid_batch_sizes_pass(self, value: str) -> None:
        assert _batch_size(value) == int(value)

    def test_main_rejects_invalid_batch_size_before_touching_settings(self) -> None:
        # argparse converts the ArgumentTypeError into a SystemExit(2); this
        # happens during parse_args, before any database/settings access.
        with pytest.raises(SystemExit) as exc:
            main(["--batch-size", "0"])
        assert exc.value.code == 2


class TestExitCodeContract:
    def test_clean_apply_is_zero(self) -> None:
        assert _sweep_exit_code(SweepReport(apply=True)) == 0

    def test_object_delete_failures_are_exit_one(self) -> None:
        report = SweepReport(apply=True, expired_object_delete_failures=1)
        assert _sweep_exit_code(report) == 1
        report = SweepReport(apply=True, orphan_delete_failures=2)
        assert _sweep_exit_code(report) == 1

    def test_dry_run_with_eligible_work_is_exit_three(self) -> None:
        assert _sweep_exit_code(SweepReport(apply=False, expired_pending_deleted=1)) == 3
        assert _sweep_exit_code(SweepReport(apply=False, orphans_deleted=1)) == 3
        assert _sweep_exit_code(SweepReport(apply=False, stale_temps_deleted=1)) == 3

    def test_clean_dry_run_is_zero(self) -> None:
        assert _sweep_exit_code(SweepReport(apply=False)) == 0

    def test_missing_objects_are_work_remaining_in_either_mode(self) -> None:
        def _missing() -> MissingObject:
            return MissingObject(
                business_id=uuid.uuid4(), asset_id=uuid.uuid4(), variant="canonical"
            )

        assert _sweep_exit_code(SweepReport(apply=True, missing_objects=[_missing()])) == 3
        assert _sweep_exit_code(SweepReport(apply=False, missing_objects=[_missing()])) == 3

    def test_failures_take_precedence_over_remaining_work(self) -> None:
        report = SweepReport(
            apply=True,
            orphan_delete_failures=1,
            missing_objects=[
                MissingObject(business_id=uuid.uuid4(), asset_id=uuid.uuid4(), variant="canonical")
            ],
        )
        assert _sweep_exit_code(report) == 1

    def test_malformed_keys_are_work_remaining_in_both_modes(self) -> None:
        # Malformed/unknown entries are never auto-deleted → unresolved work
        # in dry run AND apply (round-2 finding 4).
        assert _sweep_exit_code(SweepReport(apply=False, malformed_keys=1)) == 3
        assert _sweep_exit_code(SweepReport(apply=True, malformed_keys=1)) == 3

    def test_malformed_keys_yield_to_a_higher_priority_failure(self) -> None:
        report = SweepReport(apply=True, malformed_keys=2, orphan_delete_failures=1)
        assert _sweep_exit_code(report) == 1


class TestVerifyExitAndHygiene:
    def test_consistent_report_is_zero(self) -> None:
        assert _verify_exit_code(VerifyReport()) == 0

    def test_any_finding_is_one(self) -> None:
        report = VerifyReport(
            findings=[
                VerifyFinding(uuid.uuid4(), uuid.uuid4(), "canonical", "unreadable"),
            ]
        )
        assert _verify_exit_code(report) == 1

    def test_malformed_only_report_is_one(self) -> None:
        assert _verify_exit_code(VerifyReport(malformed_keys=1)) == 1

    def test_print_verify_emits_no_key_path_or_checksum(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = VerifyReport(
            findings=[
                VerifyFinding(uuid.uuid4(), uuid.uuid4(), "w320", "checksum_mismatch"),
                VerifyFinding(uuid.uuid4(), uuid.uuid4(), "canonical", "unreadable"),
            ],
            malformed_keys=1,
        )
        _print_verify(report)
        out = capsys.readouterr().out
        assert ".webp" not in out
        assert "/" not in out  # no filesystem paths or keys
        assert "checksum_mismatch" in out  # the kind label is fine
        assert "unreadable" in out
