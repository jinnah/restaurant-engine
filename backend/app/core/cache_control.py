"""Response cache policy for the versioned API (M2A, ADR-010).

Every ``/api/v1`` response is ``Cache-Control: no-store``: the API serves
session-, CSRF-, and account-bearing payloads, and no public caching
decision has been made yet (that decision belongs to the storefront
milestone, M4). Health probes are deliberately not covered.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIX = "/api/v1"


class NoStoreApiMiddleware:
    """Pure ASGI middleware stamping no-store on API responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_with_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_no_store)
