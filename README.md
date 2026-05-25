# Dox — Agent Governance & Drift Observatory

Dox is a cloud-agnostic runtime governance control plane for agentic AI systems. It provides:

- **Agent registry** — lifecycle management and heartbeat tracking
- **Event ingestion** — real-time canonical event stream from instrumented agents
- **Drift detection** — behavioral baseline comparison and deviation alerting
- **Policy evaluation** — configurable sentinel rules with automated interventions
- **Quota enforcement** — per-tenant daily/monthly usage limits
- **Compliance reporting** — unified governance reports across services
- **Webhook notifications** — outbound alerts to external systems
- **LangGraph workflows** — orchestrated human-review, replay, and sentinel-response flows
- **Agent SDK** — lightweight fire-and-forget instrumentation library

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.12 |
| Poetry | 1.8+ |
| Docker + Compose | any recent |

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/baatasaari/Dox.git
cd Dox
poetry install
```

### 2. Configure environment

Copy the example below into a `.env` file in the repo root. The only required value that has no default is `DOX_DATABASE__URL`.

```dotenv
# .env
DOX_ENVIRONMENT=dev
DOX_SECRET_KEY=change-me-in-production

# PostgreSQL (matches docker-compose defaults)
DOX_DATABASE__URL=postgresql+asyncpg://dox:dox_dev@localhost:5432/dox

# Redis (matches docker-compose defaults)
DOX_REDIS__URL=redis://localhost:6379/0

# Adapters
DOX_ADAPTERS__EVENT_BUS=redis_streams
DOX_ADAPTERS__OBJECT_STORE=local_fs
DOX_ADAPTERS__LOCAL_FS_PATH=local_fs_store
DOX_ADAPTERS__SECRET_STORE=env
DOX_ADAPTERS__METRICS=noop

# Auth
DOX_AUTH__ACCESS_TOKEN_EXPIRE_MINUTES=30
DOX_AUTH__ALGORITHM=HS256
```

All settings use the `DOX_` prefix and `__` as a nested delimiter (handled by pydantic-settings).

### 3. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL 16, Redis 7, and Adminer (DB browser at <http://localhost:8080>).

Wait for the health checks to pass (usually < 10 s):

```bash
docker compose ps   # all services should show "healthy"
```

### 4. Run migrations

```bash
poetry run alembic upgrade head
```

Eight migrations create the full schema (events, users, tenants, sentinel tables, baselines, webhooks, quotas, agent profiles, audit entries).

### 5. Seed development fixtures

```bash
poetry run python -m scripts.seed_fixtures --tenant demo
```

This loads the default governance policies from `config/policies/` and prints a summary.

### 6. Start the API server

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| Endpoint | Description |
|----------|-------------|
| <http://localhost:8000/docs> | Interactive Swagger UI |
| <http://localhost:8000/redoc> | ReDoc documentation |
| <http://localhost:8000/healthz> | Liveness probe |
| <http://localhost:8000/readyz> | Readiness probe |
| <http://localhost:8000/openapi.json> | Raw OpenAPI schema |

---

## Running tests

### Unit tests only (no Docker required)

```bash
make test-unit
# or
poetry run pytest tests/unit/ --no-cov
```

### Full test suite

Docker services must be running and migrations applied.

```bash
make test
# or
poetry run pytest
```

The suite runs **1372 tests** in ~30 s and enforces 80 % line coverage across all packages.

### Lint and type-check

```bash
make lint
# or
poetry run ruff check .
poetry run mypy common/ services/
```

Auto-fix ruff violations:

```bash
make lint-fix
# or
poetry run ruff check --fix .
```

---

## Project layout

```
Dox/
├── app/                        # FastAPI gateway (assembles all routers)
│   └── main.py
├── common/                     # Shared library
│   ├── adapters/               # EventBus, ObjectStore, Metrics, SecretStore
│   ├── api/                    # Exception handlers
│   ├── audit/                  # Audit integrity helpers
│   ├── auth/                   # JWT tokens, password hashing, dependencies
│   ├── config/                 # Pydantic-settings (env / .env)
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── db.py                   # Async SQLAlchemy session factory
│   ├── policy_config.py        # YAML policy loader
│   └── tracing_middleware.py   # OpenTelemetry request tracing
├── config/
│   └── policies/               # Default governance policy YAML files
├── services/                   # One sub-package per bounded context
│   ├── audit/                  # Audit trail
│   ├── auth/                   # Token issuance
│   ├── compliance/             # Reporting
│   ├── drift/                  # Behavioral drift detection
│   ├── ingestion/              # Event ingestion pipeline
│   ├── notify/                 # Webhook delivery
│   ├── policy/                 # Policy CRUD + evaluation
│   ├── query/                  # Event query API
│   ├── quota/                  # Rate limiting & quota
│   ├── registry/               # Agent registry
│   ├── sentinel/               # Alert management
│   ├── tenant/                 # Tenant management
│   └── users/                  # User management
├── sdk/python/dox_sdk/         # Agent instrumentation SDK
├── langgraph_workflows/        # LangGraph governance workflows
│   ├── drift_analysis/
│   ├── human_review/
│   ├── replay/
│   └── sentinels/
├── scripts/
│   └── seed_fixtures.py        # Dev data seeder
├── tests/
│   ├── unit/                   # ~1300 fast tests (no Docker)
│   └── integration/            # ~70 cross-service tests
├── alembic/                    # DB migrations
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

---

## API overview

All endpoints under `/v1/` require a `Bearer` JWT token. Obtain one via:

```bash
curl -s -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "secret"}' \
  | jq -r .access_token
```

### Role access matrix

| Role | Accessible services |
|------|-------------------|
| `admin` | Everything |
| `operator` | Ingestion, registry, sentinel, drift, compliance, query, quota, audit, policy, notify |
| `viewer` | Sentinel, drift, compliance, query, quota, audit |
| `agent` | Ingestion, registry |

### Key routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/auth/token` | Obtain JWT (public) |
| `POST` | `/v1/events` | Ingest a single event |
| `POST` | `/v1/events/batch` | Ingest a batch of events |
| `GET` | `/v1/agents` | List registered agents |
| `GET` | `/v1/sentinel/alerts` | List governance alerts |
| `GET` | `/v1/drift` | List drift records |
| `GET` | `/v1/compliance/{tenant_id}` | Compliance report |
| `GET` | `/v1/tenants` | List tenants (admin only) |
| `GET` | `/v1/users` | List users (admin only) |

See `/docs` for the full interactive reference.

---

## Agent SDK

Instrument an agent with the bundled SDK:

```python
from dox_sdk import DoxClientBuilder

client = (
    DoxClientBuilder()
    .base_url("http://localhost:8000")
    .api_key("your-agent-jwt")
    .tenant_id("acme")
    .agent_id("my-agent-v1")
    .raise_on_error(False)   # fire-and-forget; never blocks the agent
    .build()
)

await client.emit(event)         # single event
await client.emit_batch(events)  # batch
await client.aclose()
```

---

## Default governance policies

Two policy sets ship in `config/policies/`:

| File | Policies |
|------|---------|
| `default_governance.yaml` | tool misuse warning, injection termination, trajectory review, cost-loop pause, hallucination warning |
| `strict_security.yaml` | delegation isolation, bias memory rollback, regulatory termination |

Load them into a tenant with:

```bash
poetry run python -m scripts.seed_fixtures --tenant acme
```

Or import programmatically:

```python
from common.policy_config import load_for_tenant

policies = load_for_tenant("config/policies/default_governance.yaml", tenant_id="acme")
```

---

## Makefile targets

```
make install        Install dependencies
make dev            Start Docker services and run migrations
make stop           Stop Docker services
make clean          Destroy Docker volumes (destructive)
make migrate        Run Alembic migrations (upgrade head)
make migrate-create Create a new migration: make migrate-create name=<name>
make test           Full test suite (requires Docker)
make test-unit      Unit tests only (no Docker)
make lint           ruff + mypy
make lint-fix       ruff --fix
make seed           Load development fixtures
```
