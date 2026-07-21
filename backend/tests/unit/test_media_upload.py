"""Bounded multipart upload handling (M3C, ADR-017 upload correction).

Exercises the two independent byte bounds, Content-Length validation, and
single-file-part extraction by calling the helpers directly with a small
``file_max_bytes`` — no 10 MiB HTTP bodies, no database.
"""

import asyncio
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any

import pytest
from starlette.requests import Request

from app.core.errors import ApiError
from app.domains.media.policies import MULTIPART_OVERHEAD_BYTES
from app.domains.media.upload import extract_single_file, read_bounded_body

FILE_CAP = 1000  # small cap for fast, deterministic bound tests


def _request(body: bytes, *, content_type: str, content_length: str | None) -> Request:
    headers = [(b"content-type", content_type.encode())]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {"type": "http", "method": "POST", "headers": headers}
    return Request(scope, receive)


def _multipart(file_bytes: bytes, *, boundary: str = "BOUNDARY", name: str = "file") -> bytes:
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="x.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    return head + file_bytes + f"\r\n--{boundary}--\r\n".encode()


def _read(request: Request) -> SpooledTemporaryFile[bytes]:
    return asyncio.run(read_bounded_body(request, file_max_bytes=FILE_CAP))


class TestReadBoundedBody:
    def test_missing_content_length_is_422(self) -> None:
        request = _request(b"data", content_type="multipart/form-data", content_length=None)
        with pytest.raises(ApiError) as exc:
            _read(request)
        assert exc.value.status_code == 422

    def test_malformed_content_length_is_422(self) -> None:
        request = _request(b"data", content_type="x", content_length="not-a-number")
        with pytest.raises(ApiError) as exc:
            _read(request)
        assert exc.value.status_code == 422

    def test_header_declared_overflow_is_413(self) -> None:
        over = FILE_CAP + MULTIPART_OVERHEAD_BYTES + 1
        request = _request(b"x", content_type="x", content_length=str(over))
        with pytest.raises(ApiError) as exc:
            _read(request)
        assert exc.value.status_code == 413

    def test_streamed_overflow_is_413(self) -> None:
        # Content-Length lies small; the actual stream overruns the bound.
        body = b"x" * (FILE_CAP + MULTIPART_OVERHEAD_BYTES + 50)
        request = _request(body, content_type="x", content_length="10")
        with pytest.raises(ApiError) as exc:
            _read(request)
        assert exc.value.status_code == 413

    def test_within_bounds_body_is_returned(self) -> None:
        body = b"x" * 200
        request = _request(body, content_type="x", content_length=str(len(body)))
        buffer = _read(request)
        buffer.seek(0)
        assert buffer.read() == body
        buffer.close()


class TestExtractSingleFile:
    def _extract(self, body: bytes, *, content_type: str, tmp_path: Path) -> object:
        request = _request(body, content_type=content_type, content_length=str(len(body)))
        buffer = _read(request)
        try:
            # extract_single_file now takes the captured Content-Type header
            # string (worker-thread safe), not the live Request (correction 2).
            return extract_single_file(
                content_type, buffer, file_max_bytes=FILE_CAP, work_dir=tmp_path
            )
        finally:
            buffer.close()

    def test_extracts_single_file_part(self, tmp_path: Path) -> None:
        body = _multipart(b"hello-image-bytes")
        result = self._extract(
            body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
        )
        assert result.filename == "x.jpg"  # type: ignore[attr-defined]
        assert result.path.read_bytes() == b"hello-image-bytes"  # type: ignore[attr-defined]

    def test_exact_maximum_file_is_accepted(self, tmp_path: Path) -> None:
        body = _multipart(b"y" * FILE_CAP)
        result = self._extract(
            body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
        )
        assert len(result.path.read_bytes()) == FILE_CAP  # type: ignore[attr-defined]

    def test_file_over_cap_is_413(self, tmp_path: Path) -> None:
        # The file part exceeds the file cap but stays within request+overhead.
        body = _multipart(b"z" * (FILE_CAP + 100))
        with pytest.raises(ApiError) as exc:
            self._extract(
                body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
            )
        assert exc.value.status_code == 413

    def test_non_multipart_content_type_is_422(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc:
            self._extract(b"plain", content_type="application/json", tmp_path=tmp_path)
        assert exc.value.status_code == 422

    def test_wrong_field_name_is_422(self, tmp_path: Path) -> None:
        body = _multipart(b"data", name="not_file")
        with pytest.raises(ApiError) as exc:
            self._extract(
                body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
            )
        assert exc.value.status_code == 422

    def test_extra_field_is_rejected(self, tmp_path: Path) -> None:
        boundary = "BOUNDARY"
        body = (
            _multipart(b"data").rstrip(f"\r\n--{boundary}--\r\n".encode())
            + f"\r\n--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="extra"\r\n\r\nvalue'
            + f"\r\n--{boundary}--\r\n".encode()
        )
        with pytest.raises(ApiError) as exc:
            self._extract(
                body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
            )
        assert exc.value.status_code == 422

    def test_empty_file_part_is_422(self, tmp_path: Path) -> None:
        body = _multipart(b"")
        with pytest.raises(ApiError) as exc:
            self._extract(
                body, content_type="multipart/form-data; boundary=BOUNDARY", tmp_path=tmp_path
            )
        assert exc.value.status_code == 422

    def test_copy_failure_removes_the_partial_upload_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If shutil.copyfileobj raises after opening the target, the partial
        # upload-* scratch file must be removed (round-2 finding 2).
        import shutil

        def _boom(src: object, dst: Any, *args: object, **kwargs: object) -> None:
            dst.write(b"partial")
            raise OSError("copy failed mid-write")

        monkeypatch.setattr(shutil, "copyfileobj", _boom)
        body = _multipart(b"hello-image-bytes")
        request = _request(
            body,
            content_type="multipart/form-data; boundary=BOUNDARY",
            content_length=str(len(body)),
        )
        buffer = _read(request)
        try:
            with pytest.raises(OSError, match="copy failed"):
                extract_single_file(
                    "multipart/form-data; boundary=BOUNDARY",
                    buffer,
                    file_max_bytes=FILE_CAP,
                    work_dir=tmp_path,
                )
        finally:
            buffer.close()
        assert list(tmp_path.glob("upload-*")) == []
