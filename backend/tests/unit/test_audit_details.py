"""Audit detail schemas: closed key set, provably secret-free (M2A).

The recorder only accepts these models, so this test bounds everything
that can ever appear in the audit ``details`` column.
"""

from pydantic import BaseModel

from app.domains.audit import details as details_module
from app.domains.audit.details import AuditDetails

# No audit detail field name may ever contain one of these fragments.
_DENYLISTED_FRAGMENTS = ("password", "token", "hash", "secret", "cookie", "credential")


def _all_detail_models() -> list[type[AuditDetails]]:
    models = [
        obj
        for obj in vars(details_module).values()
        if isinstance(obj, type) and issubclass(obj, AuditDetails) and obj is not AuditDetails
    ]
    assert models, "expected at least one audit detail schema"
    return models


def test_detail_field_names_never_reference_secrets() -> None:
    for model in _all_detail_models():
        for field_name in model.model_fields:
            lowered = field_name.lower()
            for fragment in _DENYLISTED_FRAGMENTS:
                assert fragment not in lowered, (
                    f"{model.__name__}.{field_name} looks like it could carry "
                    f"a secret ('{fragment}'); audit details must never do so"
                )


def test_detail_models_reject_unknown_keys() -> None:
    # extra='forbid' is what makes the key set closed; verify it holds for
    # every schema rather than trusting inheritance configuration silently.
    for model in _all_detail_models():
        assert model.model_config.get("extra") == "forbid", model.__name__


def test_detail_models_are_immutable() -> None:
    for model in _all_detail_models():
        assert model.model_config.get("frozen") is True, model.__name__


def test_base_class_is_a_pydantic_model() -> None:
    assert issubclass(AuditDetails, BaseModel)
