# Resilient Retrieval

Sonar uses normal HTTP retrieval as its fast path. Difficult HTML can
optionally escalate through Scrapling HTTP and then CloakBrowser.

## Enable Locally

Install optional dependencies:

```bash
uv sync --extra dev --extra resilient --extra browser
```

Enable the backends in `config/sonar.toml`:

```toml
[retrieval]
scrapling_enabled = true
browser_enabled = true
cloakbrowser_enabled = true
thin_text_min_chars = 200
browser_wait_until = "domcontentloaded"
```

Build the browser-capable Streamable HTTP MCP image with:

```bash
docker build --target browser-runtime -t sonar:browser .
docker run --rm -p 8000:8000 -v sonar-data:/data sonar:browser
```

## Fallback Behavior

Fallback is deterministic and based on transport failures, selected access
restriction responses, restriction markers, application-shell HTML, and thin
text.

- Browser fallback applies only to HTML.
- PDFs and other non-HTML documents never trigger browser fallback.
- A later fallback failure does not discard an earlier usable result.
- Missing optional dependencies are recorded as failed attempts without
  preventing lightweight startup.
- `force_refresh=true` bypasses cached retrieval and extraction.

## Policy

Policy is evaluated before every live backend attempt. Robots denial, robots
lookup failure, domain denial, backend denial, and local-network denial are
terminal and never trigger escalation.

Keep `policy.respect_robots` and `policy.deny_local_networks` enabled unless the
deployment has a reviewed reason to change them. Per-domain policies can limit
allowed backends. See the [Configuration Reference](../reference/configuration.md).

Retrieval responses include provenance fields such as the selected backend,
whether rendering occurred, attempts, warnings, and fallback reason.
