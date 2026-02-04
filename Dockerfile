FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

# 安装项目依赖
RUN uv sync --no-dev

# 安装项目
RUN uv pip install -e .

# 设置入口点
ENTRYPOINT ["ptest"]
CMD ["--help"]
