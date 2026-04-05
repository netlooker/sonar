# Quick Start

1. Install dependencies:

```bash
uv sync --extra dev
```

2. Copy the example config:

```bash
cp config/sonar.example.toml config/sonar.toml
```

3. Adjust the SearxNG URL and database path.

4. Run the API:

```bash
uv run sonar-api
```

5. Or run the MCP server:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml uv run sonar-mcp
```

## Container Build

Build:

```bash
docker build -t sonar:latest .
```

Run:

```bash
docker run --rm -p 8001:8001 \
  -e SONAR_CONFIG=/app/config/sonar.toml \
  -v "$(pwd)/config/sonar.toml:/app/config/sonar.toml:ro" \
  -v sonar-data:/data \
  sonar:latest
```

## Compose Stack

Start Sonar with a colocated SearxNG backend:

```bash
docker compose up --build
```

The compose stack mounts:

- `config/sonar.compose.example.toml` into the Sonar container
- `searxng/settings.yml` into the SearxNG container
- a named volume for `/data/sonar.sqlite`
