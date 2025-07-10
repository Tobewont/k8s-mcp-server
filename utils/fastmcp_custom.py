"""
自定义 FastMCP 类
基于用户提供的代码，添加 create_app 方法
"""

from __future__ import annotations as _annotations

import sys
from typing import Any

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

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.routing import Mount, Route

from .lowlevel import McpServer

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

    def sse_app(self) -> Starlette:
        """Return an instance of the SSE server app."""
        sse = SseServerTransport(self.settings.message_path)

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

        # Define the middleware
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"], # Allows all origins
                allow_credentials=True,
                allow_methods=["*"], # Allows all methods
                allow_headers=["*"], # Allows all headers
            )
        ]

        return Starlette(
            debug=self.settings.debug,
            routes=[
                Route(self.settings.sse_path, endpoint=handle_sse),
                Mount(self.settings.message_path, app=sse.handle_post_message),
            ],
            middleware=middleware # Add the middleware here
        )

    def create_app(self) -> Starlette:
        """创建应用实例，兼容原有的 create_app 调用"""
        return self.sse_app() 