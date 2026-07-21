"""Resource-lifecycle durability for media processing and preview (M3C).

Final correction 5 / round-2 finding 1: a failing encode leaves no scratch
file (on save AND on the post-save read), and the preview stream is closed
through the real StreamingResponse/ASGI lifecycle on completion, on read
failure, and on client-disconnect cancellation.
"""

import asyncio
import io
from collections.abc import Generator
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send

from app.domains.media.processing import _encode
from app.domains.media.router_admin import _stream_and_close


class _PartialImage:
    """A stand-in image whose ``save`` writes partial bytes then fails."""

    width = 10
    height = 10

    def save(self, handle: Any, **_kwargs: Any) -> None:
        handle.write(b"partial-webp-bytes")
        raise OSError("disk full during encode")


class _GoodImage:
    """A stand-in image whose ``save`` succeeds (write completes)."""

    width = 10
    height = 10

    def save(self, handle: Any, **_kwargs: Any) -> None:
        handle.write(b"ok-webp-bytes")


def test_encode_failure_leaves_no_scratch_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="disk full"):
        _encode(_PartialImage(), "canonical", tmp_path)  # type: ignore[arg-type]
    assert list(tmp_path.glob("encode-*")) == []


def test_encode_post_save_read_failure_leaves_no_scratch_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The save succeeds (file written) but the subsequent read raises: the
    # partial encode-* file must still be removed (round-2 finding 2).
    def _boom(_self: Path) -> bytes:
        raise OSError("read failure after save")

    monkeypatch.setattr(Path, "read_bytes", _boom)
    with pytest.raises(OSError, match="read failure after save"):
        _encode(_GoodImage(), "canonical", tmp_path)  # type: ignore[arg-type]
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


# --- Real StreamingResponse/ASGI-lifecycle closure (round-2 finding 1) -------


class _CountingStream:
    """Tracks close() calls; tolerates being closed more than once."""

    def __init__(self, data: bytes, *, fail_after: int | None = None) -> None:
        self._buf = io.BytesIO(data)
        self.close_count = 0
        self._reads = 0
        self._fail_after = fail_after

    def read(self, size: int) -> bytes:
        self._reads += 1
        if self._fail_after is not None and self._reads > self._fail_after:
            raise OSError("mid-stream read failure")
        return self._buf.read(size)

    def close(self) -> None:
        self.close_count += 1


def _preview_response(stream: _CountingStream) -> StreamingResponse:
    """Mirror the route's StreamingResponse wiring (generator + background)."""
    return StreamingResponse(
        _stream_and_close(cast(BinaryIO, stream)),
        media_type="image/webp",
        background=BackgroundTask(stream.close),
    )


async def _drive_asgi(response: StreamingResponse, *, disconnect: bool) -> list[Message]:
    """Drive a response through the ASGI protocol; optionally disconnect."""
    sent: list[Message] = []
    first = {"delivered": False}

    async def receive() -> Message:
        if disconnect:
            return {"type": "http.disconnect"}
        if not first["delivered"]:
            first["delivered"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "headers": []}
    await response(scope, cast(Receive, receive), cast(Send, send))
    return sent


def test_streaming_response_closes_stream_on_normal_completion() -> None:
    stream = _CountingStream(b"webp-body-bytes")
    asyncio.run(_drive_asgi(_preview_response(stream), disconnect=False))
    # Closed at least once (generator finally + background safety net); the
    # double close is tolerated safely.
    assert stream.close_count >= 1


def test_streaming_response_closes_stream_on_read_failure() -> None:
    # A mid-stream read failure may surface out of the ASGI call or be
    # handled internally by the framework; either way the stream must close.
    stream = _CountingStream(b"x" * (256 * 1024), fail_after=1)
    try:
        asyncio.run(_drive_asgi(_preview_response(stream), disconnect=False))
    except OSError:
        pass
    assert stream.close_count >= 1


def test_streaming_response_closes_stream_on_client_disconnect() -> None:
    stream = _CountingStream(b"y" * (256 * 1024))
    asyncio.run(_drive_asgi(_preview_response(stream), disconnect=True))
    assert stream.close_count >= 1
