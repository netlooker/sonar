# Configuration Reference

Sonar uses TOML configuration with environment-variable overrides.

## Loading and Precedence

Configuration is resolved in this order:

1. An explicit application-level config path, when supplied.
2. `SONAR_CONFIG`.
3. `config/sonar.toml`.
4. `sonar.toml`.
5. Built-in defaults when no file exists.

An optional secrets overlay is loaded first, then the main config overrides it,
then environment variables override both. The default secrets overlay path is
`secrets/sonar.secrets.toml`; change it with `SONAR_SECRETS_FILE`.

Start from [`../../config/sonar.example.toml`](../../config/sonar.example.toml)
for local use or
[`../../config/sonar.compose.example.toml`](../../config/sonar.compose.example.toml)
for Compose.

## Sections

### `searxng`

- `base_url`: SearxNG endpoint.
- `api_key`: optional provider key.
- `authorization_header`: optional complete authorization header.

Environment: `SONAR_SEARXNG_BASE_URL`, `SONAR_SEARXNG_API_KEY`,
`SONAR_SEARXNG_AUTHORIZATION_HEADER`.

### `database`

- `path`: SQLite database path.

Environment: `SONAR_DB`.

### `http`

- `host`, `port`: HTTP API bind address.
- `auth_mode`: reserved HTTP authentication mode setting.

Environment: `SONAR_HTTP_HOST`, `SONAR_HTTP_PORT`, `SONAR_HTTP_AUTH_MODE`.

### `cache`

- `search_ttl_seconds`: search-result cache lifetime.
- `extract_ttl_seconds`: extraction cache lifetime.

Environment: `SONAR_SEARCH_TTL_SECONDS`, `SONAR_EXTRACT_TTL_SECONDS`.

### `fetch`

- `connect_timeout_seconds`, `read_timeout_seconds`: retrieval timeouts.
- `max_body_bytes`: maximum fetched body size.
- `user_agent`: retrieval user agent.

Environment: `SONAR_CONNECT_TIMEOUT_SECONDS`, `SONAR_READ_TIMEOUT_SECONDS`,
`SONAR_MAX_BODY_BYTES`, `SONAR_USER_AGENT`.

### `retrieval`

- `scrapling_enabled`: allow Scrapling HTTP fallback.
- `browser_enabled`: allow browser fallback.
- `cloakbrowser_enabled`: allow CloakBrowser backend use.
- `thin_text_min_chars`: threshold used by fallback heuristics.
- `browser_wait_until`: browser navigation wait strategy.

Environment: `SONAR_SCRAPLING_ENABLED`, `SONAR_BROWSER_ENABLED`,
`SONAR_CLOAKBROWSER_ENABLED`, `SONAR_THIN_TEXT_MIN_CHARS`,
`SONAR_BROWSER_WAIT_UNTIL`.

### `policy`

- `respect_robots`: enforce robots policy.
- `deny_local_networks`: deny local and private targets.

Environment: `SONAR_RESPECT_ROBOTS`, `SONAR_DENY_LOCAL_NETWORKS`.

### `domains`

Each `[domains."example.com"]` table can set:

- `allow`: permit or deny the domain.
- `allowed_backends`: restrict retrieval backend names.

### `search`

- `default_limit`: default result count.
- `max_limit`: maximum result count.

Environment: `SONAR_DEFAULT_LIMIT`, `SONAR_MAX_LIMIT`.

### `embeddings`

- `enabled`: enable topic relevance filtering.
- `base_url`: OpenAI-compatible API base URL.
- `api_key`: provider key.
- `model`: embeddings model.
- `similarity_threshold`: minimum topic similarity.

Environment: `SONAR_EMBEDDINGS_ENABLED`, `SONAR_EMBEDDINGS_BASE_URL`,
`SONAR_EMBEDDINGS_API_KEY` or `OPENAI_API_KEY`, `SONAR_EMBEDDINGS_MODEL`,
`SONAR_TOPIC_RELEVANCE_THRESHOLD`.

### `ranking.domain_priors`

Maps domains to numeric score bonuses used during deterministic ranking.

## MCP Environment

MCP server settings are environment-only:

- `SONAR_MCP_TRANSPORT`: `stdio` or `streamable-http`; default `stdio`.
- `SONAR_MCP_HOST`: HTTP bind host; default `127.0.0.1`.
- `SONAR_MCP_PORT`: HTTP bind port; default `8000`.
- `SONAR_MCP_PATH`: Streamable HTTP path; default `/mcp`.
- `SONAR_MCP_STATELESS_HTTP`: stateless HTTP mode; default `true`.
