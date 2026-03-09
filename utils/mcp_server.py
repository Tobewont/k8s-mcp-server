"""
MCP 服务器实现
"""
from __future__ import annotations as _annotations

import contextvars
import logging
import warnings
from contextlib import AsyncExitStack
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.shared.session import RequestResponder
from mcp import types, McpError
from mcp.server.lowlevel.server import Server as _Server, LifespanResultT
from starlette.types import Scope

from .context import RequestContext

logger = logging.getLogger(__name__)

request_ctx: contextvars.ContextVar[RequestContext[ServerSession, Any]] = (
    contextvars.ContextVar("request_ctx")
)


class McpServer(_Server):

    async def run(
            self,
            read_stream: MemoryObjectReceiveStream[types.JSONRPCMessage | Exception],
            write_stream: MemoryObjectSendStream[types.JSONRPCMessage],
            initialization_options: InitializationOptions,
            raise_exceptions: bool = False,
            scope: Scope | None = None
    ):
        logger.debug("scope: %s", scope)
        logger.debug("=" * 100)
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))
            session = await stack.enter_async_context(
                ServerSession(read_stream, write_stream, initialization_options)
            )
            async with anyio.create_task_group() as tg:
                async for message in session.incoming_messages:
                    tg.start_soon(
                        self._handle_message,
                        message,
                        session,
                        lifespan_context,
                        raise_exceptions,
                        scope
                    )

    @property
    def request_context(self) -> RequestContext[ServerSession, LifespanResultT]:
        """If called outside of a request context, this will raise a LookupError."""
        return request_ctx.get()

    async def _handle_message(
        self,
        message: RequestResponder[types.ClientRequest, types.ServerResult]
        | types.ClientNotification
        | Exception,
        session: ServerSession,
        lifespan_context: LifespanResultT,
        raise_exceptions: bool = False,
        scope: Scope | None = None
    ):
        with warnings.catch_warnings(record=True) as w:
            match message:  # type: ignore[reportMatchNotExhaustive]
                case (
                    RequestResponder(request=types.ClientRequest(root=req)) as responder
                ):
                    with responder:
                        await self._handle_request(
                            message, req, session, lifespan_context, raise_exceptions, scope
                        )
                case types.ClientNotification(root=notify):
                    await self._handle_notification(notify)

            for warning in w:
                logger.info(f"Warning: {warning.category.__name__}: {warning.message}")

    async def _handle_request(
        self,
        message: RequestResponder[types.ClientRequest, types.ServerResult],
        req: Any,
        session: ServerSession,
        lifespan_context: LifespanResultT,
        raise_exceptions: bool,
        scope: Scope | None = None
    ):
        logger.info(f"Processing request of type {type(req).__name__}")
        if type(req) in self.request_handlers:
            handler = self.request_handlers[type(req)]
            logger.debug(f"Dispatching request of type {type(req).__name__}")

            token = None
            try:
                token = request_ctx.set(
                    RequestContext(
                        message.request_id,
                        message.request_meta,
                        session,
                        lifespan_context,
                        scope=scope
                    )
                )
                response = await handler(req)
            except McpError as err:
                response = err.error
            except Exception as err:
                if raise_exceptions:
                    raise err
                response = types.ErrorData(code=0, message=str(err), data=None)
            finally:
                if token is not None:
                    request_ctx.reset(token)

            await message.respond(response)
        else:
            await message.respond(
                types.ErrorData(
                    code=types.METHOD_NOT_FOUND,
                    message="Method not found",
                )
            )

        logger.debug("Response sent")
