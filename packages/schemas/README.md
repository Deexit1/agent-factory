# packages/schemas

Shared Pydantic v2 contracts for agent hand-offs: `TaskSpec`, `AcceptanceCriterion`,
`FailureReport`, `BusinessCase`. See [docs/04-agent-specs.md](../../docs/04-agent-specs.md).

Each model carries a `schema_version` field; breaking changes bump the version rather than
mutating a shape in place.

```bash
pip install -e ".[dev]"
pytest
schemas export             # writes JSON Schema files to apps/web/src/generated/schemas
schemas export --out DIR   # or a custom directory
```
