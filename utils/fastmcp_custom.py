"""
自定义 FastMCP 类
基于用户提供的代码，添加 create_app 方法
"""

from __future__ import annotations as _annotations

import logging as _logging
from typing import Any, Sequence

# 修复 anyio 的类型注解兼容性问题
def _fix_anyio_compatibility():
    """修复 anyio.create_memory_object_stream 的泛型语法兼容性问题"""
    try:
        import anyio
        
        # 保存原始函数
        _original_create = anyio.create_memory_object_stream
        
        # 创建包装函数
        class MemoryObjectStreamWrapper:
            def __init__(self, original_func):
                self._original_func = original_func
            
            def __call__(self, *args, **kwargs):
                return self._original_func(*args, **kwargs)
            
            def __getitem__(self, item):
                # 当使用泛型语法时，仍然返回包装后的函数
                return self
        
        # 替换原始函数
        anyio.create_memory_object_stream = MemoryObjectStreamWrapper(_original_create)
        
    except ImportError:
        pass

# 在导入 MCP 模块之前执行修复
_fix_anyio_compatibility()

from mcp.server import FastMCP as _FastMCP
from mcp.server.fastmcp.prompts import PromptManager
from mcp.server.fastmcp.resources import ResourceManager
from mcp.server.fastmcp.server import Settings, lifespan_wrapper
from mcp.server.fastmcp.tools import ToolManager
from mcp.server.fastmcp.utilities.logging import configure_logging, get_logger
from mcp.server.lowlevel.server import lifespan as default_lifespan
from mcp.server.sse import SseServerTransport
from mcp.types import Tool as MCPTool

from config import MCP_ADMIN_API_PREFIX, MCP_AUTH_ENABLED, MCP_HEALTH_PATH
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .admin_routes import admin_cleanup_revoked, admin_issue_token, admin_list_revoked, admin_list_users, admin_revoke_token, internal_upload_kubeconfig
from .jwt_middleware import JWTAuthMiddleware
from .mcp_server import McpServer

logger = get_logger(__name__)


class FastMCP(_FastMCP):

    def __init__(
        self, name: str | None = None, instructions: str | None = None, **settings: Any
    ):
        self.settings = Settings(**settings)

        self._mcp_server = McpServer(
            name=name or "FastMCP",
            instructions=instructions,
            lifespan=lifespan_wrapper(self, self.settings.lifespan) if self.settings.lifespan else default_lifespan,
        )
        self._tool_manager = ToolManager(
            warn_on_duplicate_tools=self.settings.warn_on_duplicate_tools
        )
        self._resource_manager = ResourceManager(
            warn_on_duplicate_resources=self.settings.warn_on_duplicate_resources
        )
        self._prompt_manager = PromptManager(
            warn_on_duplicate_prompts=self.settings.warn_on_duplicate_prompts
        )
        self.dependencies = self.settings.dependencies

        # Set up MCP protocol handlers
        self._setup_handlers()

        # Configure logging
        configure_logging(self.settings.log_level)

    @property
    def mcp_server(self) -> McpServer:
        return self._mcp_server

    # ---- tool 可见性过滤 ----

    _AUTH_ONLY_TOOLS = {"whoami", "admin_manage_users", "admin_manage_profiles"}

    def _get_allowed_tools(self) -> set[str] | None:
        """
        根据当前请求的用户 profile 返回允许的 tool 名称集合。
        返回 None 表示不过滤（admin 角色）。
        返回 set 表示只允许集合中的 tool。
        """
        if not MCP_AUTH_ENABLED:
            return set()  # 空集 → list_tools 中排除 _AUTH_ONLY_TOOLS
        from utils.auth_context import current_role, current_user_id
        from utils.permission_profiles import get_profile_allowed_tools, get_user_access_grants

        role = current_role.get()
        uid = current_user_id.get()
        if role == "admin":
            return None

        if not uid:
            return {"whoami"}

        access = get_user_access_grants(uid, active_only=True)
        if not access:
            return {"whoami"}

        allowed: set[str] = {"whoami"}
        seen_profiles: set[str] = set()
        for grant in access:
            pname = grant.get("profile")
            if pname and pname not in seen_profiles:
                seen_profiles.add(pname)
                tools = get_profile_allowed_tools(pname)
                if tools:
                    allowed.update(tools)
        return allowed

    def _filter_tools(self, tools: list, allowed: set[str] | None) -> list:
        """
        过滤 tool 列表：
        - None: 不过滤（admin / 已认证管理员）
        - 空集: 认证未启用，隐藏 auth-only tools
        - 非空集: 只保留集合中的 tools
        """
        if allowed is None:
            return tools
        if not allowed:
            return [t for t in tools if t.name not in self._AUTH_ONLY_TOOLS]
        return [t for t in tools if t.name in allowed]

    async def list_tools(self) -> list[MCPTool]:
        """按用户 profile 过滤可见 tool 列表"""
        all_tools = self._tool_manager.list_tools()
        allowed = self._get_allowed_tools()
        filtered = self._filter_tools(all_tools, allowed)
        return [
            MCPTool(
                name=info.name,
                description=info.description,
                inputSchema=info.parameters,
            )
            for info in filtered
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Sequence[Any] | dict[str, Any]:
        """调用 tool 时校验权限"""
        allowed = self._get_allowed_tools()
        if allowed is not None:
            if not allowed:
                if name in self._AUTH_ONLY_TOOLS:
                    from mcp import McpError
                    from mcp.types import ErrorData, METHOD_NOT_FOUND
                    raise McpError(ErrorData(code=METHOD_NOT_FOUND, message=f"工具 '{name}' 不可用（认证未启用）"))
            elif name not in allowed:
                from mcp import McpError
                from mcp.types import ErrorData, METHOD_NOT_FOUND
                raise McpError(ErrorData(code=METHOD_NOT_FOUND, message=f"工具 '{name}' 不可用（权限不足）"))
        context = self.get_context()
        return await self._tool_manager.call_tool(name, arguments, context=context, convert_result=True)

    def sse_app(self) -> Starlette:
        """Return an instance of the SSE server app with SSE and Streamable HTTP support."""
        sse = SseServerTransport(self.settings.message_path)
        streamable_path = getattr(
            self.settings, "streamable_http_path", "/streamable"
        )

        async def handle_sse(request: Request) -> None:
            try:
                async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,  # type: ignore[reportPrivateUsage]
                ) as streams:
                    await self.mcp_server.run(
                        streams[0],
                        streams[1],
                        self._mcp_server.create_initialization_options(),
                        scope=request.scope
                    )
            except Exception as e:
                logger.error(f"Error in SSE connection: {e}")
                raise

        # Streamable HTTP: 单一端点同时支持 GET(SSE) 和 POST(消息)
        streamable_transport = SseServerTransport(streamable_path)

        async def handle_streamable_get(request: Request) -> None:
            try:
                async with streamable_transport.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,  # type: ignore[reportPrivateUsage]
                ) as streams:
                    await self.mcp_server.run(
                        streams[0],
                        streams[1],
                        self._mcp_server.create_initialization_options(),
                        scope=request.scope
                    )
            except Exception as e:
                logger.error(f"Error in Streamable HTTP GET: {e}")
                raise

        class StreamableASGIApp:
            """ASGI 应用：按 HTTP 方法分发，不返回值由 send 发送响应"""

            async def __call__(self, scope, receive, send):
                if scope["type"] != "http":
                    return
                request = Request(scope, receive, send)
                if request.method == "GET":
                    await handle_streamable_get(request)
                else:
                    await streamable_transport.handle_post_message(
                        scope, receive, send
                    )

        async def health(_request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        admin_prefix = MCP_ADMIN_API_PREFIX

        # CORS 在外层，JWT 在内层（请求先过 CORS 再过鉴权）
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            Middleware(JWTAuthMiddleware),
        ]

        routes = [
            Route(MCP_HEALTH_PATH, endpoint=health, methods=["GET"]),
            Route(
                admin_prefix + "/tokens/issue",
                endpoint=admin_issue_token,
                methods=["POST"],
            ),
            Route(
                admin_prefix + "/tokens/revoke",
                endpoint=admin_revoke_token,
                methods=["POST"],
            ),
            Route(
                admin_prefix + "/tokens/revoked",
                endpoint=admin_list_revoked,
                methods=["GET"],
            ),
            Route(
                admin_prefix + "/users",
                endpoint=admin_list_users,
                methods=["GET"],
            ),
            Route(
                admin_prefix + "/tokens/cleanup",
                endpoint=admin_cleanup_revoked,
                methods=["POST"],
            ),
            Route(
                admin_prefix + "/kubeconfigs/upload",
                endpoint=internal_upload_kubeconfig,
                methods=["POST"],
            ),
            Route(self.settings.sse_path, endpoint=handle_sse, methods=["GET"]),
            Mount(self.settings.message_path, app=sse.handle_post_message),
            # Streamable HTTP: ASGI 应用，GET=SSE 连接，POST=消息
            Route(
                streamable_path,
                endpoint=StreamableASGIApp(),
                methods=["GET", "POST"],
            ),
        ]

        return Starlette(
            debug=self.settings.debug,
            routes=routes,
            middleware=middleware,
        )

    def create_app(self) -> Starlette:
        """创建应用实例，兼容原有的 create_app 调用"""
        return self.sse_app() 