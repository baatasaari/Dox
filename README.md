# Dox — Agent Governance & Drift Observatory

> **Runtime governance for every AI agent.** Observe every action, enforce policy in real time, and produce tamper-evident audit trails — without adding latency to the agent.

![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![Tests](https://img.shields.io/badge/tests-1372-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-80%25%2B-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## What is Dox?

Dox is a cloud-agnostic governance control plane that sits alongside your AI agent fleet. Every agent action is emitted as a **canonical event** to Dox; Dox evaluates it against configurable sentinel policies and intervenes in real time — blocking tool calls, pausing agents, requesting human review, or terminating runaway executions — all while maintaining a cryptographically-chained audit log.

```
  ┌─────────────────────────────────────────────────────────┐
  │                    Your AI Agents                       │
  │   LangGraph · CrewAI · AutoGen · Custom                 │
  └────────────────────────┬────────────────────────────────┘
                           │  dox_sdk.emit(event)   [3 lines]
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    Dox Control Plane                    │
  │                                                         │
  │  ┌───────────┐  ┌────────────┐  ┌─────────────────┐   │
  │  │  Ingest   │→ │  Sentinel  │→ │   Intervene      │   │
  │  │  Events   │  │  Evaluate  │  │ block/pause/     │   │
  │  │  (Redis)  │  │  Policies  │  │ terminate/review │   │
  │  └───────────┘  └────────────┘  └─────────────────┘   │
  │         │                                               │
  │  ┌──────▼──────────────────────────────────────────┐   │
  │  │  PostgreSQL — events · agents · audit · quotas  │   │
  │  └─────────────────────────────────────────────────┘   │
  │                                                         │
  │  Drift Detection · Compliance Reports · Webhooks        │
  │  LangGraph Workflows · Multi-tenant RBAC               │
  └─────────────────────────────────────────────────────────┘
                           │
                           ▼
               Slack / PagerDuty / SIEM
               EU AI Act evidence packs
```

---

## Features

| Capability | Description |
|---|---|
| **Event ingestion** | Single and batch ingest; 35 canonical event types; Redis Streams fanout |
| **Policy engine** | YAML-configured sentinel rules; 10 automated intervention actions |
| **Drift detection** | Behavioral baseline comparison; deviation alerting per agent |
| **Quota enforcement** | Per-tenant daily/monthly limits; hard block on breach |
| **Compliance reporting** | Unified governance report across all services per tenant |
| **Webhook delivery** | Outbound alert notifications to Slack, PagerDuty, or any HTTP target |
| **Audit trail** | Cryptographically-chained append-only log; tamper verification endpoint |
| **LangGraph workflows** | Orchestrated human-review, replay, drift-analysis, and sentinel-response flows |
| **Agent SDK** | Python SDK; 3-line integration; non-blocking async fire-and-forget |
| **Multi-tenant RBAC** | `admin / operator / viewer / agent` roles; per-tenant isolation |

---

## Requirements

| Tool | Version |
|---|---|
| Python | 3.12 |
| Poetry | 1.8+ |
| Docker + Compose | any recent |
| PostgreSQL | 16 (via Docker or native) |
| Redis | 7 (via Docker or native) |

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/baatasaari/Dox.git
cd Dox
poetry install
```

### 2. Configure environment

```bash
cp .env.example .env
```

Minimal `.env` (Docker defaults wired in):

```dotenv
DOX_ENVIRONMENT=dev
DOX_SECRET_KEY=change-me-in-production

# PostgreSQL
DOX_DATABASE__URL=postgresql+asyncpg://dox:dox_dev@localhost:5432/dox

# Redis
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

All settings use the `DOX_` prefix with `__` as the nested delimiter (pydantic-settings convention).

### 3. Start infrastructure

```bash
docker compose up -d
docker compose ps   # wait until all services show "healthy"
```

Starts PostgreSQL 16, Redis 7, and Adminer (DB browser at <http://localhost:8080>).

### 4. Run migrations

```bash
poetry run alembic upgrade head
```

Eight migrations create the full schema: events, users, tenants, sentinel tables, baselines, webhooks, quotas, agent profiles, audit entries.

### 5. Seed development fixtures

```bash
poetry run python -m scripts.seed_fixtures --tenant demo
```

Loads the default governance policies from `config/policies/` into the `demo` tenant.

### 6. Start the API server

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| URL | Description |
|---|---|
| <http://localhost:8000/docs> | Interactive Swagger UI |
| <http://localhost:8000/redoc> | ReDoc documentation |
| <http://localhost:8000/openapi.json> | Raw OpenAPI schema |
| <http://localhost:8000/healthz> | Liveness probe |
| <http://localhost:8000/readyz> | Readiness probe |

---

## API overview

All `/v1/` endpoints require a `Bearer` JWT. Obtain one:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "secret"}' \
  | jq -r .access_token)
```

### Role access matrix

| Role | Accessible services |
|---|---|
| `admin` | Everything — tenants, users, and all below |
| `operator` | Ingestion, registry, sentinel, drift, compliance, query, quota, audit, policy, notify |
| `viewer` | Sentinel, drift, compliance, query, quota, audit (read-only) |
| `agent` | Ingestion, registry (emit events and heartbeat) |

### Key routes

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/auth/token` | public | Obtain JWT |
| `POST` | `/v1/tenants` | admin | Create tenant |
| `POST` | `/v1/users` | admin | Create user |
| `POST` | `/v1/agents/register` | agent, operator, admin | Register agent |
| `PUT` | `/v1/agents/{id}/heartbeat` | agent, operator, admin | Heartbeat |
| `POST` | `/v1/events` | agent, operator, admin | Ingest single event |
| `POST` | `/v1/events/batch` | agent, operator, admin | Ingest batch |
| `GET` | `/v1/events` | viewer+ | Query events |
| `POST` | `/v1/sentinel/policies` | operator, admin | Create policy |
| `GET` | `/v1/sentinel/alerts` | viewer+ | List alerts |
| `PUT` | `/v1/sentinel/alerts/{id}/resolve` | operator, admin | Resolve alert |
| `POST` | `/v1/policies/evaluate` | operator, admin | Evaluate policy |
| `POST` | `/v1/drift/baselines` | operator, admin | Compute baseline |
| `GET` | `/v1/drift` | viewer+ | List drift records |
| `GET` | `/v1/compliance/{tenant_id}` | viewer+ | Compliance report |
| `POST` | `/v1/notify/webhooks` | operator, admin | Register webhook |
| `GET` | `/v1/audit` | viewer+ | Audit log |
| `GET` | `/v1/audit/verify` | viewer+ | Verify chain integrity |
| `GET` | `/v1/quota/{tenant_id}` | viewer+ | Get quota usage |

See `/docs` for the full interactive reference including all request/response schemas.

---

## Canonical event schema

Every agent action is emitted as a `CanonicalEvent`. Required fields:

```python
{
  "event_id":       "<uuid4>",          # unique per event
  "trace_id":       "<uuid4>",          # links events in one agent run
  "session_id":     "<uuid4>",          # agent session boundary
  "correlation_id": "<uuid4>",          # cross-agent correlation
  "agent_id":       "my-agent-v1",
  "tenant_id":      "acme",
  "event_type":     "tool_call_started", # see full list below
  "environment":    "dev",              # dev | test | staging | prod
  "client_timestamp": "2026-07-04T12:00:00Z",
  "payload":        { ... }             # event-specific data
}
```

### Supported event types (35)

```
agent_started          agent_stopped          agent_paused
agent_resumed          agent_error            tool_call_started
tool_call_completed    tool_call_failed       tool_call_blocked
model_called           model_response         model_error
memory_read            memory_write           memory_deleted
human_input_requested  human_input_received   policy_evaluated
policy_violated        sentinel_triggered     sentinel_resolved
quota_checked          quota_exceeded         drift_detected
drift_resolved         session_started        session_ended
span_started           span_ended             log_message
custom_event           agent_delegated        agent_recalled
checkpoint_saved       checkpoint_restored
```

---

## Sentinel policies

### Intervention actions (10)

| Action | Effect |
|---|---|
| `warn` | Log warning; agent continues |
| `allow` | Explicit allow; audit only |
| `redact` | Redact sensitive content from event payload |
| `block_tool_call` | Block the tool call; agent receives error |
| `pause_agent` | Pause agent execution; await resume signal |
| `request_human_review` | Route to LangGraph human-review workflow |
| `force_safe_response` | Override model response with safe fallback |
| `rollback_memory_write` | Revert the memory write |
| `isolate_agent` | Remove agent from fleet; block all further actions |
| `terminate_execution` | Hard-stop the agent run |

### Sentinel types (11)

`prompt_injection` · `tool_misuse` · `cost_loop` · `trajectory_drift` · `memory_bias` · `delegation_abuse` · `regulatory_breach` · `hallucination` · `data_exfiltration` · `privilege_escalation` · `policy_violation`

### Example policy (YAML)

```yaml
# config/policies/default_governance.yaml
policies:
  - name: block-prompt-injection
    sentinel_type: prompt_injection
    severity: critical
    action: terminate_execution
    threshold: 0.85
    description: Terminate agent on high-confidence injection detection

  - name: cost-loop-circuit-breaker
    sentinel_type: cost_loop
    severity: high
    action: pause_agent
    threshold: 1000
    description: Pause agent when token spend exceeds threshold in a single session
```

Load policies into a tenant:

```bash
poetry run python -m scripts.seed_fixtures --tenant acme
```

---

## Agent SDK

Install (once the package is published, or install from source):

```bash
pip install dox-sdk
# or from this repo:
pip install -e sdk/python/
```

Instrument an agent in 3 lines:

```python
from dox_sdk import DoxClientBuilder

client = (
    DoxClientBuilder()
    .base_url("https://dox.your-org.com")
    .api_key("your-agent-jwt")
    .tenant_id("acme")
    .agent_id("research-agent-v1")
    .raise_on_error(False)   # fire-and-forget; never blocks the agent
    .build()
)

# Emit events
await client.emit(event)           # single CanonicalEvent
await client.emit_batch(events)    # list of CanonicalEvents

# Shutdown
await client.aclose()
```

`raise_on_error(False)` means a Dox outage never breaks your agent. Events are best-effort by design.

---

## LangGraph workflows

Four governance workflows ship in `langgraph_workflows/`:

| Workflow | Trigger | Purpose |
|---|---|---|
| `sentinels/` | Policy violation → `request_human_review` action | Route alert to human reviewer; await decision; resume or terminate |
| `human_review/` | Manual escalation | Structured human-in-the-loop review with approval gates |
| `drift_analysis/` | Drift alert | Automated root-cause analysis of behavioral deviation |
| `replay/` | Incident investigation | Replay a historical event sequence against current policies |

---

## Bruno API collection

A fully wired [Bruno](https://www.usebruno.com/) collection lives in `bruno/dox-api/`. It covers all 37 endpoints with pre-configured auth chaining (the `get-token` request auto-saves the JWT for all subsequent calls).

```
bruno/dox-api/
├── environments/local.bru    # baseUrl + token + tenantId variables
├── auth/                     # get-token (auto-saves JWT)
├── tenants/                  # create, list, get, get-by-slug, activate
├── users/                    # create, list, change-password
├── agents/                   # register, list, get, heartbeat
├── events/                   # ingest, ingest-batch, list, get
├── sentinel/                 # create-policy, list-policies, create-alert,
│                             #   list-alerts, resolve-alert
├── policy/                   # evaluate, get-policy
├── drift/                    # compute-baseline, list-baselines, analyze
├── compliance/               # get-report
├── quota/                    # provision, get, reset-daily
├── notify/                   # register-webhook, list-webhooks, dispatch
└── audit/                    # list-entries, verify-integrity
```

**Usage:**
1. Open Bruno → Import Collection → select `bruno/dox-api/`
2. Select the `local` environment
3. Run `auth/get-token` first — token auto-populates for all other requests

---

## Project layout

```
Dox/
├── app/
│   └── main.py                     # FastAPI gateway; assembles all 13 routers
├── common/                         # Shared internal library
│   ├── adapters/                   # EventBus (Redis), ObjectStore, Metrics, SecretStore
│   ├── auth/                       # JWT, bcrypt, FastAPI dependency injection
│   ├── config/                     # Pydantic-settings (DOX_ prefix)
│   ├── models/                     # SQLAlchemy ORM models
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   ├── db.py                       # Async SQLAlchemy session factory
│   ├── policy_config.py            # YAML policy loader
│   └── tracing_middleware.py       # OpenTelemetry request tracing
├── services/                       # One sub-package per bounded context
│   ├── auth/                       # Token issuance
│   ├── audit/                      # Audit trail + integrity verification
│   ├── compliance/                 # Cross-service governance reports
│   ├── drift/                      # Behavioral baseline + deviation detection
│   ├── ingestion/                  # Event ingest pipeline (single + batch)
│   ├── notify/                     # Webhook registration + outbound delivery
│   ├── policy/                     # Policy CRUD + evaluation endpoint
│   ├── query/                      # Event query API
│   ├── quota/                      # Usage limits + hard-block enforcement
│   ├── registry/                   # Agent registry + heartbeat
│   ├── sentinel/                   # Alert management + policy management
│   ├── tenant/                     # Tenant management (admin only)
│   └── users/                      # User management (admin only)
├── sdk/python/dox_sdk/             # Agent instrumentation SDK
│   ├── builder.py                  # Fluent DoxClientBuilder
│   ├── client.py                   # Async httpx client
│   └── result.py                   # Fire-and-forget result type
├── langgraph_workflows/            # LangGraph state-machine graphs
│   ├── sentinels/
│   ├── human_review/
│   ├── drift_analysis/
│   └── replay/
├── config/policies/                # Default governance policy YAML files
│   ├── default_governance.yaml
│   └── strict_security.yaml
├── alembic/                        # 8 versioned DB migrations
├── bruno/dox-api/                  # Bruno API collection (37 requests)
├── scripts/
│   └── seed_fixtures.py            # Dev data seeder
├── tests/
│   ├── unit/                       # ~1300 fast tests; no Docker required
│   ├── integration/                # ~70 cross-service tests; requires Docker
│   └── fixtures/
├── pitch-deck/                     # Investor and CXO pitch materials
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

---

## Running tests

### Unit tests (no Docker needed)

```bash
make test-unit
# or
poetry run pytest tests/unit/ --no-cov
```

### Full suite

Requires Docker services running and migrations applied.

```bash
make test
# or
poetry run pytest
```

Runs **1372 tests** and enforces **80%+ line coverage** across all packages.

### Lint and type-check

```bash
make lint           # ruff check + mypy
make lint-fix       # ruff check --fix
```

---

## Makefile reference

```
make install          Install Poetry dependencies
make dev              Start Docker services and run migrations
make stop             Stop Docker services
make clean            Destroy Docker volumes (destructive)
make migrate          Run Alembic migrations (upgrade head)
make migrate-create   Create a new migration:  make migrate-create name=<name>
make test             Full test suite (requires Docker)
make test-unit        Unit tests only (no Docker)
make lint             ruff + mypy
make lint-fix         ruff --fix
make seed             Load development fixtures
```

---

## Deployment

### Docker Compose (development)

```bash
docker compose up -d
poetry run alembic upgrade head
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Production checklist

- Set `DOX_SECRET_KEY` to a cryptographically random string (32+ bytes)
- Set `DOX_ENVIRONMENT=prod`
- Use a managed PostgreSQL 16 instance; set `DOX_DATABASE__URL` accordingly
- Use a managed Redis 7 instance; set `DOX_REDIS__URL` accordingly
- Run behind a TLS-terminating reverse proxy (nginx, Caddy, or cloud load balancer)
- Set `DOX_ADAPTERS__METRICS=prometheus` and scrape `/metrics` with Prometheus
- Enable structured logging: `DOX_LOG_FORMAT=json`
- Apply database migrations as part of your CI/CD pipeline: `alembic upgrade head`
- Configure `DOX_CORS__ORIGINS` to your actual frontend origins

### Kubernetes (Helm — coming in v0.2)

A Helm chart covering the API deployment, migration job, and HPA is on the roadmap. Until then, adapt the `docker-compose.yml` service definitions directly.

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `DOX_ENVIRONMENT` | `dev` | `dev \| test \| staging \| prod` |
| `DOX_SECRET_KEY` | — | JWT signing key (required) |
| `DOX_DATABASE__URL` | — | Async PostgreSQL DSN (required) |
| `DOX_REDIS__URL` | `redis://localhost:6379/0` | Redis DSN |
| `DOX_ADAPTERS__EVENT_BUS` | `redis_streams` | `redis_streams \| memory` |
| `DOX_ADAPTERS__OBJECT_STORE` | `local_fs` | `local_fs \| s3` |
| `DOX_ADAPTERS__LOCAL_FS_PATH` | `local_fs_store` | Local FS root path |
| `DOX_ADAPTERS__SECRET_STORE` | `env` | `env \| aws_secrets_manager` |
| `DOX_ADAPTERS__METRICS` | `noop` | `noop \| prometheus` |
| `DOX_AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT TTL |
| `DOX_AUTH__ALGORITHM` | `HS256` | JWT algorithm |
| `DOX_CORS__ORIGINS` | `["*"]` | Allowed CORS origins |

---

## Default governance policies

Two policy sets ship in `config/policies/`:

| File | Policies included |
|---|---|
| `default_governance.yaml` | Tool misuse warning, prompt injection termination, trajectory drift review, cost-loop pause, hallucination warning |
| `strict_security.yaml` | Delegation isolation, bias memory rollback, regulatory termination |

Load into a tenant:

```bash
poetry run python -m scripts.seed_fixtures --tenant acme
```

Or import programmatically:

```python
from common.policy_config import load_for_tenant

policies = load_for_tenant("config/policies/default_governance.yaml", tenant_id="acme")
```

---

## Contributing

1. Fork the repository and create a feature branch
2. Follow the existing bounded-context pattern: one sub-package under `services/` per feature
3. Every public function needs a unit test; integration tests for cross-service flows
4. Run `make lint` and `make test-unit` before opening a PR; CI requires 80%+ coverage
5. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, etc.)

---

## License

MIT — see [LICENSE](LICENSE) for details.
