"""Bounded multipart upload handling (M3C, ADR-017 upload correction).

The endpoint declares no body parameters, so the framework never parses
the multipart body before dependencies run (verified for FastAPI 0.139).
This module performs the parse **after** the pre-body gate, under two
independent byte bounds (final correction on upload-cap semantics):

* the raw request stream is capped at ``file cap + 64 KiB`` overhead;
* the extracted file part is capped at exactly the file cap.

``Content-Length`` is required and validated before any body byte is
read; a header-declared overflow is rejected before streaming. Exactly
one file part named ``file`` and zero other form fields are accepted.
Every temporary buffer is cleaned up on every path.
"""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any

from multipart import parse_form
from multipart.multipart import parse_options_header
from starlette.requests import ClientDisconnect, Request

from app.core.errors import ApiError, ErrorCode, PayloadTooLargeError
from app.domains.media.policies import MULTIPART_OVERHEAD_BYTES

__all__ = ["ExtractedUpload", "extract_single_file", "read_bounded_body"]

# Spool the raw body in memory up to this size, then to a temp file — never
# an unbounded in-memory buffer (ADR-017 upload correction).
_SPOOL_THRESHOLD = 1024 * 1024  # 1 MiB


@dataclass
class ExtractedUpload:
    """One extracted file part written to a caller-owned temp path."""

    path: Path
    filename: str
    content_type: str


def _validation_error(message: str) -> ApiError:
    return ApiError(422, ErrorCode.VALIDATION_ERROR, message)


async def read_bounded_body(
    request: Request, *, file_max_bytes: int
) -> SpooledTemporaryFile[bytes]:
    """Stream the request body into a bounded spooled temp file.

    Rejects a missing/malformed ``Content-Length`` (422) and a
    header-declared or streamed overflow (413) before returning. The
    caller owns closing the returned buffer.
    """
    request_max = file_max_bytes + MULTIPART_OVERHEAD_BYTES

    content_length = request.headers.get("content-length")
    if content_length is None:
        raise _validation_error("Content-Length is required for uploads.")
    try:
        declared = int(content_length)
    except ValueError as exc:
        raise _validation_error("Content-Length is malformed.") from exc
    if declared < 0:
        raise _validation_error("Content-Length is malformed.")
    if declared > request_max:
        raise PayloadTooLargeError("Upload request exceeds the maximum size.")

    buffer: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(max_size=_SPOOL_THRESHOLD)
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > request_max:
                raise PayloadTooLargeError("Upload request exceeds the maximum size.")
            buffer.write(chunk)
    except ClientDisconnect:
        buffer.close()
        raise
    except BaseException:
        buffer.close()
        raise
    buffer.seek(0)
    return buffer


def extract_single_file(
    content_type_header: str,
    body: SpooledTemporaryFile[bytes],
    *,
    file_max_bytes: int,
    work_dir: Path,
) -> ExtractedUpload:
    """Parse the bounded body and extract exactly one ``file`` part.

    Runs inside the AnyIO worker thread (final correction 2): it takes the
    already-captured ``Content-Type`` header string rather than the live
    ``Request`` object, so no request/loop state crosses the boundary.
    Enforces the file-part cap independently of the request cap, rejects
    any unexpected field or a missing/duplicate file part, and writes the
    file bytes to a fresh temp path under ``work_dir`` (caller-owned). A
    failure while copying the extracted bytes removes the partial temp
    file before propagating (final correction 5).
    """
    content_type, params = parse_options_header(content_type_header)
    if content_type != b"multipart/form-data" or b"boundary" not in params:
        raise _validation_error("Upload must be multipart/form-data with one file part.")

    files: list[Any] = []
    fields: list[Any] = []

    def _on_field(field: Any) -> None:
        fields.append(field)

    def _on_file(file: Any) -> None:
        files.append(file)

    # The raw request body is already bounded independently in
    # read_bounded_body; parse_form spills large parts to temp files, and
    # the extracted part is checked against the file cap below.
    try:
        parse_form({"Content-Type": content_type_header}, body, _on_field, _on_file)
    except Exception as exc:  # any parse failure is a client 422
        _close_files(files)
        raise _validation_error("Upload body could not be parsed.") from exc

    try:
        if fields:
            raise _validation_error("Unexpected form fields in the upload.")
        file_parts = [f for f in files if f.field_name == b"file"]
        if len(files) != 1 or len(file_parts) != 1:
            raise _validation_error("Exactly one file part named 'file' is required.")
        part = file_parts[0]
        size = int(part.size)
        if size <= 0:
            raise _validation_error("The uploaded file is empty.")
        if size > file_max_bytes:
            raise PayloadTooLargeError("The uploaded file exceeds the maximum size.")

        filename_bytes = part.file_name or b"upload"
        filename = filename_bytes.decode("utf-8", "replace")
        part_ct = part.content_type or b"application/octet-stream"
        content_type_value = (
            part_ct.decode("ascii", "replace") if isinstance(part_ct, bytes) else str(part_ct)
        )

        target = work_dir / f"upload-{uuid.uuid4()}"
        part.file_object.seek(0)
        try:
            with target.open("wb") as handle:
                shutil.copyfileobj(part.file_object, handle)
        except BaseException:
            # Partial extracted-part cleanup (final correction 5): a copy
            # failure must not leave an ``upload-*`` scratch file behind.
            target.unlink(missing_ok=True)
            raise
    finally:
        _close_files(files)

    return ExtractedUpload(path=target, filename=filename, content_type=content_type_value)


def _close_files(files: list[Any]) -> None:
    for file in files:
        try:
            file.file_object.close()
        except OSError:
            pass
