"""
Kubernetes MCP Server
通过 MCP 协议提供 Kubernetes 集群管理功能
"""

import asyncio
import argparse
import sys
from config import SSE_HOST, SSE_PORT
from mcp.server.stdio import stdio_server
from tools import mcp


async def main():
    """主函数，启动MCP服务器"""
    parser = argparse.ArgumentParser(description='Kubernetes MCP Server')
    parser.add_argument(
        '--transport',
        choices=['stdio', 'sse'],
        default='stdio',
        help='传输协议（默认: stdio）'
    )
    parser.add_argument(
        '--host',
        default=SSE_HOST,
        help='SSE服务器主机（仅在SSE模式下使用）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=SSE_PORT,
        help='SSE服务器端口（仅在SSE模式下使用）'
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
    
    elif args.transport == 'sse':
        # 使用 SSE 传输
        try:
            import uvicorn
            print(f"Starting Kubernetes MCP Server in SSE mode on {args.host}:{args.port}...", file=sys.stderr)
            
            # 创建应用
            from tools import app
            
            # 启动服务器
            config = uvicorn.Config(
                app=app,
                host=args.host,
                port=args.port,
                log_level="info"
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        except Exception as e:
            print(f"SSE mode failed: {e}", file=sys.stderr)
            print("Falling back to stdio mode...", file=sys.stderr)
            
            # 回退到 stdio 模式
            async with stdio_server() as (read_stream, write_stream):
                await mcp.mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp.mcp_server.create_initialization_options()
                )


if __name__ == "__main__":
    asyncio.run(main()) 