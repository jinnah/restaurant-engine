"""Error envelope model contract (ADR-008)."""

from app.core.errors import ErrorCode, ErrorDetail, ErrorEnvelope, FieldError


def test_envelope_serializes_to_contract_shape() -> None:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            field_errors=[FieldError(field="body.name", code="missing", message="Field required")],
            correlation_id="abc-123",
        )
    )
    assert envelope.model_dump(mode="json") == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "field_errors": [
                {"field": "body.name", "code": "missing", "message": "Field required"}
            ],
            "correlation_id": "abc-123",
            "details": None,
        }
    }


def test_field_errors_default_to_empty_list_and_details_to_none() -> None:
    detail = ErrorDetail(code=ErrorCode.NOT_FOUND, message="Not Found", correlation_id=None)
    assert detail.field_errors == []
    assert detail.details is None


def test_details_carry_structured_context() -> None:
    detail = ErrorDetail(
        code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        message="Service dependencies are unavailable.",
        correlation_id=None,
        details={"checks": {"database": "down"}},
    )
    assert detail.model_dump(mode="json")["details"] == {"checks": {"database": "down"}}


def test_error_codes_are_snake_case_strings() -> None:
    for code in ErrorCode:
        assert code.value == code.value.lower()
        assert " " not in code.value
