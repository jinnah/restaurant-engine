"""Resource-lifecycle durability for media processing and preview (M3C).

Final correction 5: a failing encode leaves no scratch file, and the
preview generator always closes its stream — on completion, on error,
and on early close (the disconnect analogue).
"""

import io
from collections.abc import Generator
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest

from app.domains.media.processing import _encode
from app.domains.media.router_admin import _stream_and_close


class _PartialImage:
    """A stand-in image whose ``save`` writes partial bytes then fails."""

    width = 10
    height = 10

    def save(self, handle: Any, **_kwargs: Any) -> None:
        handle.write(b"partial-webp-bytes")
        raise OSError("disk full during encode")


def test_encode_failure_leaves_no_scratch_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="disk full"):
        _encode(_PartialImage(), "canonical", tmp_path)  # type: ignore[arg-type]
    assert list(tmp_path.glob("encode-*")) == []


class _TrackingStream:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._buf.read(size)

    def close(self) -> None:
        self.closed = True


def test_stream_and_close_closes_after_full_read() -> None:
    stream = _TrackingStream(b"webp-body-bytes")
    assert b"".join(_stream_and_close(cast(BinaryIO, stream))) == b"webp-body-bytes"
    assert stream.closed is True


def test_stream_and_close_closes_on_early_generator_close() -> None:
    # A client disconnect surfaces as GeneratorExit on the next send/close.
    stream = _TrackingStream(b"x" * (200 * 1024))
    generator = cast(Generator[bytes, None, None], _stream_and_close(cast(BinaryIO, stream)))
    next(generator)  # start streaming
    generator.close()  # simulate disconnect
    assert stream.closed is True


def test_stream_and_close_closes_on_read_error() -> None:
    class _FailingStream:
        closed = False

        def read(self, _size: int) -> bytes:
            raise OSError("mid-stream read failure")

        def close(self) -> None:
            self.closed = True

    stream = _FailingStream()
    with pytest.raises(OSError, match="mid-stream"):
        list(_stream_and_close(cast(BinaryIO, stream)))
    assert stream.closed is True
