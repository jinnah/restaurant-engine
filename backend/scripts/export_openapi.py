"""Export the canonical OpenAPI document (ADR-009).

The exported JSON is the committed API contract that the generated
TypeScript client is built from, so the output must be byte-identical on
every machine: keys are sorted (independent of FastAPI's insertion order),
indentation is two spaces, the encoding is UTF-8, and line endings are LF
with one trailing newline — on Windows too.

The export needs no environment, no ``.env``, and no database: settings are
explicit in-code placeholders (implicit sources disabled) and the SQLAlchemy
engine connects lazily.

Usage (from the repository root)::

    uv run --directory backend python -m scripts.export_openapi [output_path]

Default output: ``packages/api-client/openapi.json``.
"""

import json
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.core.settings import AppEnv, Settings
from app.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = _REPO_ROOT / "packages" / "api-client" / "openapi.json"

# Deliberately not a credential: the engine never connects during export.
_PLACEHOLDER_DATABASE_URL = "postgresql+psycopg://export:export@127.0.0.1:5433/openapi_export"


class _ExplicitSettings(Settings):
    """Settings built from explicit values only.

    Mirrors ``tests/conftest.ExplicitSettings`` (scripts must not import
    test helpers): all implicit pydantic-settings sources are disabled so a
    developer's environment or ``.env`` can never influence the export.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def canonical_openapi_json() -> str:
    """Render the application's OpenAPI document in canonical form."""
    settings = _ExplicitSettings.model_validate(
        {
            "app_env": AppEnv.TEST,
            "database_url": _PLACEHOLDER_DATABASE_URL,
            "log_level": "WARNING",
        }
    )
    app = create_app(settings)
    document = app.openapi()
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> None:
    output = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_openapi_json())


if __name__ == "__main__":
    main(sys.argv)
