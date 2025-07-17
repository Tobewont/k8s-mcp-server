from __future__ import annotations as _annotations

import contextvars
import logging
import warnings
from contextlib import AsyncExitStack
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import base64
import json
import yaml

from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession

from mcp.shared.session import RequestResponder

from mcp import types, McpError
from mcp.server.lowlevel.server import Server as _Server, LifespanResultT
from starlette.types import Scope

from .context import RequestContext

from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)



request_ctx: contextvars.ContextVar[RequestContext[ServerSession, Any]] = (
    contextvars.ContextVar("request_ctx")
)


def parse_secret_data(data: dict) -> dict:
    """
    将 base64 编码的 Secret data 字段解码为明文，并自动尝试解析 yaml/json 内容。
    返回格式：{key: 明文或解析后的对象}
    """
    result = {}
    for k, v in (data or {}).items():
        try:
            decoded = base64.b64decode(v).decode('utf-8')
            # 尝试解析为 yaml/json
            try:
                # 先尝试 json
                result[k] = json.loads(decoded)
            except Exception:
                try:
                    # 再尝试 yaml
                    result[k] = yaml.safe_load(decoded)
                except Exception:
                    result[k] = decoded
        except Exception as e:
            result[k] = f"<解码失败: {e}>"
    return result


def to_local_time_str(dt, tz_offset_hours: int = 8) -> str:
    """
    将时间戳（datetime 或 ISO 字符串）转换为指定时区的字符串，默认东八区。
    :param dt: datetime 对象或 ISO 格式字符串
    :param tz_offset_hours: 时区偏移（小时），默认 8（北京时间）
    :return: 格式化后的时间字符串
    """
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            return dt
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(timezone(timedelta(hours=tz_offset_hours)))
    return local.strftime('%Y-%m-%d %H:%M:%S')


class McpServer(_Server):

    async def run(
            self,
            read_stream: MemoryObjectReceiveStream[types.JSONRPCMessage | Exception],
            write_stream: MemoryObjectSendStream[types.JSONRPCMessage],
            initialization_options: InitializationOptions,
            # When False, exceptions are returned as messages to the client.
            # When True, exceptions are raised, which will cause the server to shut down
            # but also make tracing exceptions much easier during testing and when using
            # in-process servers.
            raise_exceptions: bool = False,
            scope: Scope | None = None
    ):
        print(f"scope: {scope}")
        print("="*100)
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
            # TODO(Marcelo): We should be checking if message is Exception here.
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
                # Set our global state that can be retrieved via
                # app.get_request_context()
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
                # Reset the global state after we are done
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
