# Secrets

Use this directory for local-only TOML overlays. Files are ignored except for
this guide and `*.example.toml` templates.

Start from `sonar.secrets.example.toml` when configuring optional SearxNG or
embeddings credentials:

```bash
cp secrets/sonar.secrets.example.toml secrets/sonar.secrets.toml
```

The default overlay path is `secrets/sonar.secrets.toml`. Set
`SONAR_SECRETS_FILE` to use another path. Environment variables can also supply
credentials; see the [configuration reference](../docs/reference/configuration.md).

Do not commit real credentials.
