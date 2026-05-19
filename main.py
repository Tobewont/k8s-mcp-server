"""
Kubernetes MCP Server
通过 MCP 协议提供 Kubernetes 集群管理功能
"""

import asyncio
import argparse
import sys
from config import SSE_HOST, SSE_PORT, LOG_LEVEL
from mcp.server.stdio import stdio_server
from tools import mcp


async def main():
    """主函数，启动MCP服务器"""
    parser = argparse.ArgumentParser(description='Kubernetes MCP Server')
    parser.add_argument(
        '--transport',
        choices=['stdio', 'sse', 'streamable'],
        default='stdio',
        help='传输协议（默认: stdio）'
    )
    parser.add_argument(
        '--host',
        default=SSE_HOST,
        help='HTTP服务器主机（仅在sse/streamable模式下使用）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=SSE_PORT,
        help='HTTP服务器端口（仅在sse/streamable模式下使用）'
    )
    
    args = parser.parse_args()
    
    if args.transport == 'stdio':
        # 使用 stdio 传输
        print("Starting Kubernetes MCP Server in stdio mode...", file=sys.stderr)
        async with stdio_server() as (read_stream, write_stream):
            await mcp.mcp_server.run(
                read_stream,
                write_stream,
                mcp.mcp_server.create_initialization_options()
            )
    
    elif args.transport in ('sse', 'streamable'):
        # 使用 HTTP 传输（SSE 或 Streamable HTTP）
        try:
            import uvicorn
            print(
                f"Starting Kubernetes MCP Server in {args.transport} mode on {args.host}:{args.port}...",
                file=sys.stderr,
            )
            
            # 创建应用
            from tools import app
            
            # 启动服务器
            config = uvicorn.Config(
                app=app,
                host=args.host,
                port=args.port,
                log_level=LOG_LEVEL
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        except Exception as e:
            if isinstance(e, ImportError):
                print("HTTP mode failed (missing uvicorn). Install: uv sync", file=sys.stderr)
            else:
                print(f"HTTP mode failed: {e}", file=sys.stderr)
            print("Falling back to stdio mode...", file=sys.stderr)
            async with stdio_server() as (read_stream, write_stream):
                await mcp.mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp.mcp_server.create_initialization_options()
                )


def cli():
    """Console script entrypoint."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()