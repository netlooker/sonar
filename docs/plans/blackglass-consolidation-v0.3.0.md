# Sonar v0.3.0: Blackglass Consolidation Implementation Plan

## Status

- Sonar implementation complete on `codex/blackglass-consolidation-v0.3.0`;
  independent review and merge are pending.
- Target release: Sonar `v0.3.0`.
- Primary repository: Sonar.
- Source repository to migrate from: Blackglass.
- First downstream deployment: Orion.
- Orion migration and Blackglass retirement remain separate follow-up changes
  after the Sonar release is reviewed and validated.
- The untracked root-level `PRD.md` is intentionally not modified by this work.

Verified Sonar gates:

- 96 automated tests pass;
- selected retrieval/service/storage/MCP/API core branch coverage is 88%;
- changed Python files pass Ruff lint and formatting checks;
- lock verification, bytecode compilation, package build, and diff checks pass;
- stdio and Streamable HTTP MCP smokes pass;
- lightweight and browser-capable images build;
- the lightweight API and optional CloakBrowser launch smokes pass.

## Objective

Consolidate Blackglass into Sonar as an internal, deterministic, policy-aware
resilient retrieval subsystem. Sonar becomes the single agent-facing service
for search, retrieval, extraction, and prepared-source bundles.

The implementation must:

- preserve Sonar's existing `httpx` retrieval as the normal fast path;
- escalate difficult HTML through Scrapling HTTP and then CloakBrowser;
- never escalate after a policy or robots denial;
- avoid duplicate retrieval between fetch and extract;
- never invoke HTML/browser fallback for PDFs or other non-HTML documents;
- keep optional resilient dependencies out of the lightweight image;
- improve the agent-facing MCP surface and remove `sonar_sonar_*` names;
- preserve existing HTTP routes and `bundle_version = 1`;
- make migrations additive and safe for existing SQLite databases;
- retire the standalone Blackglass service after downstream validation.

## Verified Baseline

### Sonar

- `src/sonar/fetch.py` performs robots checks and an `httpx` GET.
- `sonar_fetch` currently reads the response body but discards it.
- `sonar_extract` performs a second GET and then extracts the returned body.
- `src/sonar/service_api.py` owns fetch/extract orchestration and response models.
- `src/sonar/storage.py` owns SQLite persistence and additive `_ensure_column`
  migrations.
- Sonar supports HTML, PDF, DOCX, ODT, Markdown, and text extraction.
- Sonar exposes HTTP routes and a FastMCP stdio server.
- The current FastMCP dependency supports Streamable HTTP.
- Baseline verification: `45 passed`.

### Blackglass

- Implements Scrapling HTTP retrieval and CloakBrowser rendering.
- Implements useful fallback triggers for transport failure, access restriction
  statuses, restriction markers, app-shell HTML, and thin text.
- Implements basic domain, backend, and literal-local-address policy.
- Does not implement robots checking despite exposing robots settings.
- Does not persist artifacts despite returning artifact IDs.
- Does not resolve hostnames when enforcing local-network restrictions.
- Evaluates backend policy against the requested list instead of each attempted
  backend.
- Baseline verification: `67 passed`.

### Orion

- Installs Sonar inside the main Orion image.
- OpenCode launches Sonar MCP over stdio.
- SearXNG is already a separate container.
- `/data/sonar.sqlite` is already the configured persistent database.
- OpenCode supports remote MCP configuration.
- OpenCode namespaces MCP tools as `<connection_name>_<raw_tool_name>`.
- The current `sonar` connection plus raw `sonar_*` tools produces
  `sonar_sonar_*`.
- Baseline verification: `just check` passes.

## Non-Negotiable Invariants

These invariants should be encoded in tests before or with the implementation:

1. Retrieval remains deterministic and contains no LLM calls.
2. Policy evaluation happens before every live backend attempt.
3. Explicit robots denial is terminal.
4. Robots lookup failure is terminal and must not cause backend escalation.
5. Policy denial is terminal.
6. Cross-origin redirects are re-evaluated before following or accepting them.
7. Browser fallback is considered only for HTML retrieval.
8. A successful non-HTML response is never sent to Scrapling or CloakBrowser.
9. A fetch followed by extract reuses the persisted body and does not retrieve
   the URL twice.
10. A later fallback failure never discards an earlier usable result.
11. Missing optional dependencies never prevent lightweight Sonar startup.
12. Existing SQLite databases migrate without destructive schema changes.
13. Existing HTTP routes remain available.
14. Prepared bundles remain `bundle_version = 1`.
15. Orion-visible MCP tools are named `sonar_search`, `sonar_extract`, and so on,
    never `sonar_sonar_search`.

## Scope

### In Scope

- Internal retrieval models and backend interfaces.
- Unified target, domain, backend, local-network, redirect, and robots policy.
- Existing Sonar `httpx` backend refactoring.
- Scrapling HTTP backend.
- CloakBrowser rendered backend.
- Deterministic fallback heuristics.
- Retrieval provenance and warnings.
- Body caching and fetch/extract request deduplication.
- Additive API response fields and SQLite migrations.
- Prepared-source provenance propagation.
- Lightweight and browser-capable packaging targets.
- Streamable HTTP MCP.
- Agent-facing MCP naming, schemas, descriptions, and skill guidance.
- Orion sidecar migration.
- Blackglass retirement.

### Explicitly Deferred

- Blackglass HTTP or MCP compatibility routes.
- Blackglass artifact IDs and artifact-directory semantics.
- Screenshots, traces, HAR files, and browser-session persistence.
- Caller-selected `render_only`, backend lists, or wait strategies in agent tools.
- Scrapling Dynamic support.
- CAPTCHA solving or anti-bot bypass features.
- Proxy pools, browser pools, distributed queues, and background jobs.
- Wildcard domain-policy syntax.
- Per-domain rate limiting.
- Separate body-retention configuration.
- Storing every failed retrieval attempt as a durable audit table.

## Target Package Architecture

Create an internal `src/sonar/retrieval/` package:

```text
retrieval/
  __init__.py
  models.py
  capabilities.py
  policy.py
  robots.py
  heuristics.py
  orchestrator.py
  backends/
    __init__.py
    base.py
    httpx_backend.py
    scrapling_backend.py
    cloakbrowser_backend.py
```

Responsibilities:

- `models.py`: enums and immutable retrieval result/provenance models.
- `capabilities.py`: optional dependency detection without importing heavy
  dependencies during normal startup.
- `policy.py`: target, domain, local-network, redirect, and per-backend policy.
- `robots.py`: robots retrieval, parsing, and terminal decision modeling.
- `heuristics.py`: pure fallback assessment functions.
- `orchestrator.py`: ordered backend execution and best-result selection.
- `backends/base.py`: backend protocol.
- Backend modules: dependency-localized adapters with no service/API concerns.

Keep:

- `extract.py` focused on format detection and deterministic content extraction.
- `service_api.py` focused on use-case orchestration and transport-neutral models.
- `web_api.py` and `mcp_server.py` as thin adapters.
- `storage.py` as the only SQLite owner.

## Core Retrieval Contracts

Use typed enums rather than arbitrary strings internally:

```python
class RetrievalBackend(StrEnum):
    HTTP = "http"
    SCRAPLING_HTTP = "scrapling_http"
    CLOAKBROWSER = "cloakbrowser"


class FallbackReason(StrEnum):
    TRANSPORT_FAILURE = "transport_failure"
    HTTP_401 = "http_401"
    HTTP_403 = "http_403"
    HTTP_429 = "http_429"
    RESTRICTION_MARKER = "restriction_marker"
    APP_SHELL = "app_shell"
    THIN_TEXT = "thin_text"
    EMPTY_EXTRACTION = "empty_extraction"
```

Define an immutable `RetrievalArtifact` containing:

- requested URL;
- final URL;
- status code;
- normalized content type;
- source format;
- body bytes;
- backend;
- rendered flag;
- started/completed timestamps or duration;
- retrieval attempts;
- warnings;
- fallback reason that selected the final backend;
- optional precomputed HTML extraction.

Define an immutable `RetrievalAttempt` containing:

- backend;
- outcome;
- status code;
- rendered flag;
- duration;
- warning codes;
- fallback assessment;

Do not expose raw exceptions, headers, cookies, or browser state through public
responses. Convert failures into stable warning/error codes and retain a concise
human-readable message only where operationally useful.

## Unified Policy Model

### Configuration

Add:

```toml
[retrieval]
scrapling_enabled = false
browser_enabled = false
cloakbrowser_enabled = false
thin_text_min_chars = 200
browser_wait_until = "domcontentloaded"

[policy]
respect_robots = true
deny_local_networks = true

[domains."example.com"]
allow = true
allowed_backends = ["http", "scrapling_http"]
```

Retain `[fetch]` as the owner of user agent, timeouts, and maximum body size.

### Decision Order

For each target and each backend attempt:

1. Accept only `http` and `https`.
2. Normalize and validate hostname.
3. Apply exact-host deny policy.
4. Resolve A and AAAA addresses.
5. Reject loopback, private, link-local, multicast, reserved, and unspecified
   addresses when local-network denial is enabled.
6. Check whether the attempted backend is allowed for the host.
7. Evaluate robots for the target URL and configured user agent.
8. Execute the backend.

### Redirects

- Do not blindly follow redirects across origins.
- Capture redirect targets and re-run target/domain/local/backend/robots policy
  before accepting the next request.
- Apply a bounded redirect limit.
- Preserve the final accepted URL in provenance.
- Add tests for public-to-private redirects and private-to-public redirects.

### Browser Subresources

Where CloakBrowser exposes Playwright request routing:

- abort navigation or subresource requests to denied/local targets;
- permit ordinary public subresources;
- record a warning when subresources are blocked;
- never weaken top-level target policy because the browser backend is enabled.

### Robots

- Preserve Sonar's default of respecting robots.
- `404` robots response means no declared restriction.
- Explicit disallow is terminal.
- `401` or `403` robots response remains terminal.
- Robots transport failure or `5xx` remains a terminal upstream error.
- Do not expose a per-agent robots override.
- Cache robots decisions per origin for a bounded in-process duration only if the
  implementation remains simple and fully tested; otherwise defer caching.

## Retrieval Orchestration

### Ordered Execution

For a live retrieval:

1. Run policy and robots checks.
2. Attempt existing Sonar `httpx`.
3. If successful, identify source format before fallback assessment.
4. Return non-HTML formats immediately.
5. For HTML, run normal Sonar extraction once.
6. Assess the HTTP result with deterministic fallback heuristics.
7. If needed and allowed/available, attempt Scrapling HTTP.
8. Extract and assess Scrapling HTML.
9. If still needed and allowed/available, attempt CloakBrowser.
10. Extract rendered HTML through the normal Sonar HTML extractor.
11. Select the best successful candidate.

### Candidate Selection

Selection priority:

1. successful extraction with no fallback trigger;
2. successful extraction with the greatest useful-text length;
3. usable body from the furthest successful backend;
4. best earlier usable result when later fallback fails.

Do not treat a returned `401`, `403`, or `429` page as successful evidence merely
because it contains text.

### Fallback Triggers

Fallback is allowed only for HTML or unknown responses plausibly containing
HTML, and only for:

- transport failure;
- status `401`, `403`, or `429`;
- known restriction/verification markers;
- app-shell structure plus sparse useful text;
- empty HTML extraction;
- extracted useful text below the configured threshold.

Use extracted readable text, not raw DOM text, for thin-content assessment when
extraction succeeds. This prevents navigation-heavy pages from appearing useful.

### No-Fallback Conditions

Never fallback after:

- policy denial;
- robots denial or robots lookup failure;
- body-size limit violation;
- successful PDF/DOCX/ODT/Markdown/text retrieval;
- an unsupported non-HTML content type;
- invalid URL or scheme;
- backend explicitly forbidden for the domain.

## Fetch And Extract Integration

Introduce one internal service operation that retrieves and persists a body.
Both public fetch and extract paths use it.

### `fetch_document_record`

- Return fresh cached metadata when valid.
- Otherwise perform the retrieval chain with body capture.
- Persist body and provenance.
- If HTML fallback assessment already required extraction, persist that
  extraction too.
- Continue returning metadata rather than full body text.

### `extract_document_record`

- Return fresh cached extraction when valid.
- Otherwise use a fresh cached body when available and policy still permits use.
- Only perform live retrieval when no valid cached body exists.
- Extract non-HTML formats through existing format-specific extractors.
- Reuse any HTML extraction produced during retrieval assessment.

### Cache Policy Revalidation

When serving cached body or extraction:

- re-evaluate current static domain/local/backend policy;
- do not make a new robots network request solely to serve cached content;
- reject a cached rendered artifact if its backend is no longer allowed;
- allow `force_refresh` to bypass body and extraction caches completely.

## Persistence And Migration

### Documents Table

Add nullable/default-safe columns:

```text
body BLOB
body_hash TEXT
body_expires_at REAL
retrieval_backend TEXT
rendered INTEGER NOT NULL DEFAULT 0
retrieval_attempts_json TEXT NOT NULL DEFAULT '[]'
retrieval_warnings_json TEXT NOT NULL DEFAULT '[]'
fallback_reason TEXT
```

### Prepared Bundle Sources

Add:

```text
retrieval_backend TEXT
rendered INTEGER NOT NULL DEFAULT 0
retrieval_attempts_json TEXT NOT NULL DEFAULT '[]'
retrieval_warnings_json TEXT NOT NULL DEFAULT '[]'
fallback_reason TEXT
```

### Migration Rules

- Continue using additive `_ensure_column` migrations for `v0.3.0`.
- Add defaults where SQLite permits them.
- Treat null legacy values as unknown backend, unrendered, and empty lists.
- Never infer HTTP provenance for legacy rows.
- Test migration from a fixture database created with the `v0.2.1` schema.
- Run migration and read/write tests inside a transaction-backed temporary DB.
- Do not introduce destructive table rebuilds in this release.

### Body Storage

- Store only bodies already bounded by `fetch.max_body_bytes`.
- Store the selected final artifact body, not every attempted body.
- Store `body_hash` for integrity and future deduplication.
- Keep body TTL aligned with `extract_ttl_seconds` for this release.
- Do not store browser cookies, headers, screenshots, or traces.

## Public Response Contracts

Add the following defaulted fields to `FetchResponse` and `ExtractResponse`:

```text
retrieval_backend: str | None = None
rendered: bool = false
retrieval_attempts: list[str] = []
retrieval_warnings: list[str] = []
fallback_reason: str | None = None
```

Add the same fields to prepared sources.

Rules:

- Fields are additive for HTTP clients.
- Warning values should use stable machine-readable codes.
- Existing top-level `warnings` behavior remains unchanged.
- Retrieval warnings become source warnings when building prepared sources.
- Merged HTML/direct-document sources preserve provenance from the primary
  full-text document and include relevant warnings from both retrievals.
- `bundle_version` remains `1`.

Regenerate and review `docs/openapi.json` after model changes.

## MCP Agent Surface

### Raw Tool Naming

Change raw MCP tool names from prefixed names to service-local names:

```text
health
search
fetch
extract
scrape
find_papers
prepare_paper_set
collect_sources_for_topic
```

With an OpenCode MCP connection named `sonar`, visible names become:

```text
sonar_health
sonar_search
sonar_fetch
sonar_extract
sonar_scrape
sonar_find_papers
sonar_prepare_paper_set
sonar_collect_sources_for_topic
```

Do not retain prefixed raw MCP aliases. Raw MCP naming is a deliberate `v0.3.0`
breaking change; HTTP routes are unchanged.

### Agent-Facing Parameters

Remove deployment/operator parameters from MCP schemas:

- `config_path`;
- `db_path`;
- `output_dir`.

The MCP server uses its configured runtime. Keep these parameters in internal
service requests where tests and operator integrations require them.

Retain agent-relevant controls:

- query/topic/URL/document ID;
- result counts and search filters;
- `force_refresh`;
- high-level persistence and full-text choices where useful.

### Tool Guidance

Rewrite descriptions and the Sonar skill around:

```text
known URL -> scrape
discovery -> search -> scrape selected URLs
```

Guidance:

- `scrape` is the simple one-call way to retrieve readable content from a known
  URL; no prior search or fetch call is required.
- `extract` remains available for cached document IDs and URL-based extraction.
- `fetch` is a metadata/probe operation and usually should not precede scrape
  or extract.
- `health` is operational and should not be called during normal research.
- high-level tools replace manual loops when their domain-specific behavior fits.

### MCP Response Size

Add MCP-adapter-only `include_text` and bounded `max_chars` controls to `scrape`
and `extract`.

- Persist complete extracted content regardless of MCP response truncation.
- Return document ID, provenance, extraction status, and full word count.
- Emit a stable truncation warning.
- Set a conservative default and hard maximum.
- Do not change the HTTP extraction response in this release.

### Streamable HTTP

- Refactor `build_server` to accept host, port, path, and stateless settings.
- Preserve stdio as the default transport.
- Add environment/config support for `streamable-http`.
- Use `/mcp` as the default path.
- Add a real client smoke test using `mcp.client.streamable_http`.

## Optional Dependencies And Packaging

### Python Extras

Keep core dependencies lightweight. Add:

```toml
resilient = ["scrapling[fetchers]>=..."]
browser = ["cloakbrowser>=...", "playwright>=..."]
```

Pin compatible lower and upper bounds after validating the combined dependency
graph. Regenerate `uv.lock` once, then review dependency changes explicitly.

### Capability Detection

- Detect optional modules without importing them during lightweight startup.
- Report configured, enabled, and import-available status separately.
- A configured but unavailable backend is skipped with a warning when needed.
- Core startup and normal HTTP retrieval must continue to work.

### Docker

Produce:

- `runtime`: current lightweight Sonar API/MCP-capable image without browser
  dependencies;
- `browser-runtime`: CloakBrowser-capable image with Scrapling and browser
  dependencies.

Requirements:

- use non-root runtime users where supported by the browser base image;
- use multi-stage builds;
- pin base images or digests for release artifacts;
- include a browser-launch smoke test;
- keep SearXNG separate;
- document image size and architecture limitations.

## Orion Migration

Perform only after Sonar `v0.3.0` release candidate validation.

1. Add one browser-capable Sonar service to Orion Compose.
2. Keep SearXNG as its own service.
3. Mount Orion `./data` into Sonar for SQLite and bundles.
4. Mount Orion `./secrets` read-only for configuration/secrets.
5. Enable Scrapling and CloakBrowser in Orion's Sonar config.
6. Run Sonar MCP over Streamable HTTP at `http://sonar:<port>/mcp`.
7. Change OpenCode's MCP entry to remote:

   ```json
   {
     "type": "remote",
     "url": "http://sonar:8000/mcp",
     "enabled": true,
     "oauth": false
   }
   ```

8. Remove Sonar installation and `sonar-python` from Orion's main image.
9. Preserve `/data/sonar.sqlite` without reinitializing or relocating it.
10. Update Orion security documentation to state that browser retrieval is
    enabled inside the Sonar sidecar.
11. Update seeded Sonar skill content from the released Sonar tag.

## Implementation Sequence

### Phase 0: Guardrails And Characterization

Deliverables:

- Record current API schemas and MCP tool schemas as test fixtures.
- Add tests characterizing current cache, robots, extraction, and bundle behavior.
- Add a `v0.2.1` SQLite fixture for migration testing.
- Add test helpers for fake backends and deterministic attempt recording.

Exit criteria:

- Existing behavior is captured before refactoring.
- No production behavior changes.

### Phase 1: Retrieval Models, Policy, And Heuristics

Deliverables:

- Add retrieval models and backend protocol.
- Move/refactor robots behavior into the new policy layer.
- Implement DNS-aware local-network policy and redirect checks.
- Port and harden Blackglass heuristics as pure functions.
- Add capability detection.

Exit criteria:

- Pure/unit tests cover every policy and heuristic branch.
- Existing `httpx` behavior remains unchanged through the adapter.

### Phase 2: Orchestrator And Optional Backends

Deliverables:

- Implement ordered orchestration.
- Add Scrapling adapter.
- Add CloakBrowser adapter with subresource policy where supported.
- Implement best-result selection and stable warnings.

Exit criteria:

- Backend tests use fakes by default.
- A small separately marked integration suite validates real optional backends.
- No service/API changes yet.

### Phase 3: Fetch/Extract And Storage Integration

Deliverables:

- Persist selected bodies and provenance.
- Refactor fetch and extract around one retrieval operation.
- Add additive SQLite migration.
- Reuse extraction performed during fallback assessment.
- Implement cache and `force_refresh` semantics.

Exit criteria:

- Fetch followed by extract performs one live retrieval.
- Non-HTML documents never invoke fallback.
- Legacy DB fixture migrates and remains readable.

### Phase 4: Public Contracts And Prepared Bundles

Deliverables:

- Add provenance fields to responses and prepared sources.
- Persist prepared-source provenance.
- Propagate retrieval warnings.
- Regenerate OpenAPI.

Exit criteria:

- Existing HTTP response fields remain unchanged.
- `bundle_version = 1` fixtures remain consumable.
- Old database rows and bundles produce safe defaults.

### Phase 5: MCP And Agent Ergonomics

Deliverables:

- Rename raw MCP tools.
- Remove operator-only MCP parameters.
- Add the direct-URL `scrape` facade over the shared extraction service.
- Add compact extraction controls.
- Rewrite descriptions, instructions, docs, and Sonar skill.
- Add Streamable HTTP support.

Exit criteria:

- OpenCode connection `sonar` exposes `sonar_search`, not
  `sonar_sonar_search`.
- Normal guidance is direct `scrape` for a known URL or `search -> scrape` for
  discovery.
- Remote MCP smoke tests pass.

### Phase 6: Packaging And Release Candidate

Deliverables:

- Add optional extras and lockfile changes.
- Add lightweight and browser image targets.
- Add image smoke tests and release documentation.
- Run full unit, integration, API, MCP, migration, and container suites.

Exit criteria:

- Lightweight image proves browser packages are absent.
- Browser image proves CloakBrowser can launch.
- Release candidate is usable without Orion changes.

### Phase 7: Orion Migration

Deliverables:

- Add Sonar browser sidecar.
- Switch OpenCode to remote MCP.
- Remove embedded Sonar from Orion image.
- Update configs, checks, documentation, and skill seed.

Exit criteria:

- Orion research workflow works end to end.
- Visible tool names are correct.
- Persistent Sonar state survives container recreation.
- Orion main image no longer contains Sonar/browser dependencies.

### Phase 8: Blackglass Retirement

Deliverables:

- Add final Blackglass README notice pointing to Sonar `v0.3.0+`.
- Mark Blackglass repository archived/read-only.
- Remove standalone deployment from active operational documentation.

Exit criteria:

- Orion and at least one lightweight Sonar deployment are validated.
- No known consumer depends on Blackglass HTTP/MCP routes.

## Test Matrix

### Unit Tests

- Every fallback reason.
- Restriction-marker false-positive controls.
- App-shell detection thresholds.
- Source-format gating.
- Per-backend policy.
- Exact-domain allow/deny.
- DNS-resolved local targets.
- Redirect policy.
- Capability detection.
- Best-result selection.
- Stable warning serialization.

### Service Tests

- Good HTTP HTML stays on HTTP.
- HTTP failure escalates in order.
- `401`, `403`, and `429` escalate.
- Browser-disabled behavior returns best prior result with warning.
- Missing Scrapling skips to browser only when browser is allowed/available.
- Missing browser returns best prior result.
- Robots denial and failure never escalate.
- Policy denial never invokes a backend.
- PDF/DOCX/ODT/Markdown/text never invoke fallback.
- Fetch then extract uses one live retrieval.
- `force_refresh` reruns the chain.
- Cached rendered result is rejected if browser backend becomes forbidden.

### Persistence Tests

- `v0.2.1` schema migration.
- Body/provenance round trip.
- Legacy row defaults.
- Prepared-source provenance round trip.
- Full extraction persistence when MCP output is truncated.
- No destructive migration or row loss.

### Transport Tests

- Existing HTTP routes and error mappings.
- Additive OpenAPI fields.
- Raw MCP tool names.
- MCP schemas omit operator-only fields.
- stdio MCP smoke.
- Streamable HTTP MCP smoke.
- OpenCode-visible naming smoke.

### Container Tests

- Lightweight image health and normal extraction.
- Lightweight image has no Scrapling/CloakBrowser/Playwright imports.
- Browser image health.
- Browser launch smoke.
- Browser fallback smoke against a controlled fixture site.
- Orion Compose config and end-to-end remote MCP workflow.

## Review And Quality Gates

Every phase should be reviewable independently and should not combine unrelated
refactors.

Required gates before merge:

1. `uv run pytest -q`.
2. Focused optional-backend integration tests.
3. OpenAPI regeneration with reviewed diff.
4. SQLite migration test from `v0.2.1`.
5. `uv lock --check` or equivalent frozen-lock verification.
6. Lightweight and browser image builds.
7. MCP stdio and Streamable HTTP smoke tests.
8. Orion `just check` after downstream changes.
9. End-to-end Orion research smoke test.
10. Independent code review focused on policy bypass, redirect handling, cache
    semantics, dependency boundaries, and API compatibility.

Reviewer checklist:

- Are all policy denials terminal?
- Can any redirect or browser subresource reach a denied/local address?
- Can optional imports break lightweight startup?
- Can fetch/extract still duplicate network or browser work?
- Can fallback accidentally run for a PDF or other non-HTML body?
- Are failure/warning codes stable and actionable?
- Are migrations additive and legacy-safe?
- Are full bodies bounded before SQLite persistence?
- Are public changes additive except for the intentional raw MCP rename?
- Does agent guidance discourage unnecessary calls?

## Commit And Pull Request Strategy

Prefer small, dependency-ordered commits:

1. Characterization tests and fixtures.
2. Retrieval models, policy, and heuristics.
3. Backend adapters and orchestrator.
4. Storage migration and body persistence.
5. Fetch/extract integration.
6. Public provenance and prepared bundles.
7. MCP naming, schemas, Streamable HTTP, and skill/docs.
8. Packaging and Docker targets.
9. Release notes.
10. Separate Orion repository pull request.
11. Separate Blackglass retirement pull request.

Do not mix Orion or Blackglass retirement changes into the main Sonar
implementation pull request.

## External Reviewer Handoff

Prepare a review packet for the independent Claude/Anthropic review at each
high-risk milestone rather than waiting for one final oversized review.

The packet should contain:

- the milestone objective and explicitly excluded scope;
- the commit range to review;
- changed public contracts and migration behavior;
- policy and security invariants affected by the milestone;
- exact verification commands and summarized results;
- known limitations and intentionally deferred work;
- focused questions where reviewer disagreement would change the design.

Request focused reviews after:

1. policy, redirects, robots, and local-network enforcement;
2. retrieval orchestration and backend fallback;
3. body caching, SQLite migration, and fetch/extract integration;
4. MCP contract changes and agent-facing naming;
5. Docker/browser packaging and Orion deployment.

Require findings to be resolved or explicitly documented before moving through
the next release gate. Do not treat a clean automated test run as sufficient
evidence for policy/security correctness.

## Release And Rollback

### Release

- Release as Sonar `v0.3.0`.
- Call out the raw MCP tool-name breaking change.
- Call out additive HTTP/provenance fields and SQLite migration.
- Publish lightweight and browser-capable image instructions.
- Tag Sonar before updating Orion's pinned version.

### Rollback

- Existing database columns are additive and can remain after rolling back.
- Before Orion migration, back up `/data/sonar.sqlite`.
- Roll back Orion by restoring the embedded Sonar configuration and previous
  pinned version if remote MCP validation fails.
- Do not archive Blackglass until the Orion rollback window has passed.

## Definition Of Done

The consolidation is complete when:

- Sonar owns all resilient retrieval behavior internally.
- Normal HTML remains on the existing fast path.
- Difficult HTML escalates through Scrapling and CloakBrowser according to
  policy.
- Policy and robots restrictions cannot be bypassed by fallback or redirects.
- Fetch/extract duplicate retrieval is eliminated.
- Non-HTML documents never trigger browser fallback.
- Provenance persists and appears in responses and prepared bundles.
- Lightweight deployments run without browser dependencies.
- Orion runs one agent-facing Sonar sidecar plus SearXNG.
- OpenCode displays `sonar_search`, `sonar_scrape`, and `sonar_extract`, not
  `sonar_sonar_*`.
- Agents are guided toward direct `scrape` and efficient `search -> scrape`
  workflows.
- Blackglass standalone APIs are retired and its repository is archived.
