# Getting Started Guide

Welcome to the AI Gateway platform. This guide gets you up and running locally within 10 minutes.

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local service testing)
- Git

## Local Development Setup

### 1. Clone & Configure

```bash
git clone https://github.com/SimCorp/ai-gateway.git
cd ai-gateway

# Copy environment template
cp .env.example .env

# Edit .env if you have real provider keys (optional)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-...
# Leave blank to use Ollama or local stubs
```

### 2. Start Services

```bash
docker compose -f infra/docker-compose.yml up --build
```

**First run takes ~2-3 minutes** as services healthcheck and dependencies resolve.

**Expected output:**
```
db-migrate | Successfully applied 0030 database migrations
auth | [2024-01-22 15:30:00] INFO: Ready on port 8001
admin | [2024-01-22 15:30:05] INFO: Ready on port 8005
cache | [2024-01-22 15:30:10] INFO: Ready on port 8002
litellm | [2024-01-22 15:30:15] INFO: Ready on port 8003
admin-portal | ready - started server on 0.0.0.0:3001
portal | ready - started server on 0.0.0.0:3002
hub | [nginx] signal process started
```

### 3. Access the Platform

Open your browser:

| Interface | URL | Default Credentials |
|-----------|-----|-------------------|
| **Admin Portal** | http://localhost:8080/admin-portal/ | See below |
| **Developer Portal** | http://localhost:8080/portal/ | See below |
| **Dev Hub** | http://localhost:8080/ | — |

**Development Login (local only):**
- **Email:** any email (e.g., `admin@localhost`)
- **Password:** any password (development mode auto-promotes bcrypt users to `platform_admin`)

**OIDC Login (Dex):**
1. Click "Sign in with Dex" on login page
2. Enter any email: `user@example.com`
3. Enter password: `password` (Dex default)
4. You'll have no assigned roles; ask a platform_admin to grant permissions

### 4. Verify Services

**Health Check:**
```bash
# Admin API
curl http://localhost:8080/admin/health

# Auth service
curl http://localhost:8080/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Test Session:**
```bash
# Login and get token
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@localhost",
    "password": "test",
    "remember_me": false
  }' | jq '.token'

# Use token in requests
TOKEN="..."
curl http://localhost:8080/admin/health \
  -H "Authorization: Bearer $TOKEN"
```

---

## Service Ports (Pinned)

These ports are fixed and do NOT change. If a port is already in use, stop the conflicting service.

| Service | Direct Port | Via Nginx | Purpose |
|---------|------------|-----------|---------|
| **Admin API** | 8005 | 8080/admin | Organization & user management |
| **Auth** | 8001 | 8080/auth | Login, sessions, permissions |
| **Cache** | 8002 | 8080/cache | Semantic + exact caching |
| **LiteLLM** | 8003 | 8080/litellm | Model provider routing |
| **Observability** | 8004 | 8080/observability | Usage tracking, audit logs |
| **Identity** | 8006 | 8080/identity | Agent registry, discovery |
| **Agent Relay** | 8007 | 8080/agent-relay | WebSocket relay for agents |
| **Librarian** | 8008 | 8080/librarian | Knowledge, embeddings, RAG |
| **Memory** | 8009 | 8080/memory | Agent conversation memory |
| **League** | 8010 | 8080/league | Gamified challenges |
| **Scanner** | 8011 | 8080/scanner | Security scanning (Garak, etc.) |
| **Admin Portal** | 3001 | 8080/admin-portal/ | Admin dashboard (Next.js) |
| **Developer Portal** | 3002 | 8080/portal/ | Main user interface (Next.js) |
| **PostgreSQL** | 5432 | — | Database |
| **Redis** | 6379 | — | Session store, cache |
| **Dex (OIDC)** | 5556 | — | Local identity provider |

**Access via Nginx:** Preferred for development; easier testing of multi-service requests.

**Direct Ports:** Available within Docker network and for low-level debugging.

---

## Common Tasks

### Create a New Organization Node

```bash
TOKEN="your-session-token"

# Create an area under root
curl -X POST http://localhost:8080/admin/nodes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Platform Engineering",
    "type": "area",
    "parent_id": null,
    "description": "Core platform infrastructure",
    "color": "#FF5733"
  }'
```

### Get Organization Tree

```bash
curl http://localhost:8080/admin/nodes/tree \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Grant User Permission

First, get the Entra group GUID (from Azure AD or use a placeholder for dev):

```bash
curl -X POST "http://localhost:8080/admin/nodes/{node_id}/permissions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "entra_group_id": "12345678-1234-1234-1234-123456789012",
    "entra_group_name": "platform-admins@simcorp.com",
    "role": "platform_admin"
  }'
```

### View Audit Log

```bash
# Check observability service
curl http://localhost:8080/observability/audit-log \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Test Chat Completions

```bash
curl -X POST http://localhost:8080/cache/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

---

## Development Workflow

### Running Tests

```bash
# Install test dependencies for admin service
pip install -e "services/admin[dev]"
pip install -e "services/cache[dev]"
pip install -e "services/observability[dev]"

# Run tests
pytest services/ -v

# Run specific service tests
pytest services/admin/tests/ -v --cov
```

### Code Quality

```bash
# Lint
ruff check services/

# Format
ruff format services/

# Type check (if mypy configured)
mypy services/
```

### Database Migrations

Migrations are auto-applied on startup via `db-migrate` service.

**To create a new migration:**

```bash
cd services/admin

# Create new migration file
alembic revision --autogenerate -m "describe your change"

# Review and edit migrations/versions/xxxx_description.py

# Test migration locally
docker compose -f infra/docker-compose.yml up --build db-migrate
```

### Debugging

**Tail logs:**
```bash
docker compose -f infra/docker-compose.yml logs -f admin
docker compose -f infra/docker-compose.yml logs -f cache
```

**Interactive debugging:**
```bash
# Enter service container
docker compose -f infra/docker-compose.yml exec admin /bin/bash

# Inside container: pip install ipdb, then add breakpoints
import ipdb; ipdb.set_trace()
```

**Database inspection:**
```bash
docker compose -f infra/docker-compose.yml exec postgres psql -U aigateway -d aigateway
```

---

## Key Concepts

### Path-Based Permissions

Users have roles on org nodes. Permission checks use path prefixes:
- User with `area_owner` at `/root/area` can access `/root/area`, `/root/area/unit`, `/root/area/unit/team`
- User with `team_admin` at `/root/area/unit/team` can only access that team

See `docs/guides/permission-model.md` for detailed examples.

### Session Token

After login, the response includes a `token` field. This token:
- Is a URL-safe string (no JWT encoding in dev mode)
- Is stored in Redis with a TTL (7 days for dev, 8h for admin)
- Contains user info, roles, and node assignments
- Is validated on every request via `Authorization: Bearer {token}`

### Cost Tracking

Every AI API call is logged to `cost_records`:
- Model name, token counts, cost in USD
- Associated node_id (for billing/budget rollup)
- Timestamp for MTD (month-to-date) calculations

Budget alerts trigger when spend exceeds `budget_alert_threshold` (default 0.80 = 80%).

---

## Troubleshooting

### "Connection refused" on port 8080

**Cause:** Nginx hub service not ready.

**Solution:**
```bash
# Wait for healthcheck
docker compose -f infra/docker-compose.yml logs hub

# Restart hub
docker compose -f infra/docker-compose.yml restart hub
```

### "Session expired or invalid" after login

**Cause:** Token not found in Redis or Redis connection failed.

**Solution:**
```bash
# Check Redis
docker compose -f infra/docker-compose.yml exec redis redis-cli PING

# Verify session was stored
docker compose -f infra/docker-compose.yml exec redis redis-cli KEYS "session:*"

# Re-login
```

### Database migration fails

**Cause:** Schema conflict or migration version mismatch.

**Solution:**
```bash
# Check migration status
docker compose -f infra/docker-compose.yml exec admin alembic current

# View migration history
docker compose -f infra/docker-compose.yml exec admin alembic history

# Reset to clean state (dev only!)
# rm -rf data/postgres/
# docker compose down -v
# docker compose up --build
```

### Services slow or timeout

**Cause:** Insufficient resources or service unhealthy.

**Solution:**
```bash
# Check all healthchecks
docker compose -f infra/docker-compose.yml ps

# Restart failing services
docker compose -f infra/docker-compose.yml restart SERVICENAME

# Increase Docker resources (Mac: 4GB RAM, 2 CPUs minimum)
```

---

## Next Steps

1. **Explore the API:** Read `docs/api/nodes.md` for organization endpoints
2. **Understand Permissions:** See `docs/guides/permission-model.md`
3. **Review Architecture:** Check `docs/architecture/services.md` for service overview
4. **Try the Portal:** Log in and explore the admin dashboard
5. **Write Tests:** See `services/admin/tests/` for examples

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| `docs/api/nodes.md` | Organization nodes API reference |
| `docs/api/auth.md` | Authentication, sessions, OIDC |
| `docs/architecture/services.md` | Service overview and request paths |
| `docs/architecture/org-model.md` | Data model, materialized path, permissions |
| `docs/guides/permission-model.md` | Path-based access control in detail |
| `docs/guides/migration-from-v1.md` | Upgrading from Areas/Units/Teams |
| `README.md` (root) | Project overview and quick start |

---

## Support

- **Issues:** Create an issue on GitHub
- **Questions:** Slack #ai-gateway or email devops@simcorp.com
- **Code Review:** Submit PR to master branch; CI will run tests
