# memoire-mcp standalone HTTP server image.
# Bake the package + deps + a streamable-http entrypoint so it can be
# deployed as its own Kubernetes Deployment + Service and consumed by
# any MCP client over a URL.
#
# Build:
#   docker build -t memoire-mcp:latest mcp
#
# Run:
#   docker run --rm -p 8000:8000 \
#     -e MEMOIRE_API_URL=https://api.memoire.example.com \
#     -e MEMOIRE_PAT=pat_... \
#     -e MEMOIRE_MCP_TRANSPORT=streamable-http \
#     memoire-mcp:latest
#
# Then connect any MCP client at http://<host>:8000/mcp.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first to keep the layer cache hot when only source
# changes.
COPY pyproject.toml ./
COPY memoire_mcp/ ./memoire_mcp/
RUN pip install --no-cache-dir .

# HTTP transport defaults. Override with env in the container runtime.
ENV MEMOIRE_MCP_TRANSPORT=streamable-http \
    MEMOIRE_MCP_HOST=0.0.0.0 \
    MEMOIRE_MCP_PORT=8000 \
    MEMOIRE_MCP_PATH=/mcp

EXPOSE 8000

# Drop root.
RUN useradd --system --uid 1000 --create-home memoire
USER 1000

ENTRYPOINT ["memoire-mcp"]
