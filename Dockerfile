FROM python:3.12-slim

# 设置工作目录
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app

# 复制项目文件
COPY . /app

# 安装依赖
RUN uv sync --frozen --no-dev && \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 启动服务
ENTRYPOINT ["k8s-mcp-server"]
CMD ["--transport", "streamable"]
