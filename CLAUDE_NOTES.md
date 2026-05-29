# Claude Notes

Operator-facing notes from agent runs. Appended in reverse-chronological order.

---

## 2026-05-29 — Investigation: Terraform IaC cell for hosting cells as MCP servers (issue #24)

**Queue task:** task_59scrq
**Trigger:** Issue #24 from operator JSBaxter.

### What the issue asks

> I'd like you to investigate your ability to create a new cell. The cell should focus on
> terraform IaC for hosting cells as MCP servers.

This investigation covers: what the cell would do, what it would contain, what Terraform
resources it needs, how cells run as MCP servers over the network, and recommended next steps.

**Note:** Per CI rules, I cannot scaffold a new cell — that requires the operator to run
`uvx copier copy gh:JSBaxter/stem-cell <new-cell-path>` per `REPRODUCTION.md`. This note
describes what to build so you can spawn and configure it.

---

### Background: how cells currently run as MCP servers

All cells in the colony today use **stdio transport** — the MCP client (Claude Desktop,
Claude Code, or another cell) spawns the server process locally via a command in `.mcp.json`:

```json
{
  "mcpServers": {
    "atlas": { "command": "uv", "args": ["run", "atlas", "--transport", "stdio"] }
  }
}
```

This works well for single-machine setups but means every client that wants to talk to atlas
must have the Python environment and database locally. For a distributed colony where cells
talk to each other over the network (or where Claude.ai / external agents connect), cells
need to run with **SSE or HTTP streaming transport** as persistent services.

FastMCP (which all cells use) already supports this:
```python
# Current stdio (local)
mcp.run(transport="stdio")

# Hosted SSE (network, persistent)
mcp.run(transport="sse", host="0.0.0.0", port=8080)

# Hosted HTTP streaming (network, persistent — preferred for new deployments)
mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

Switching atlas from stdio to hosted transport is independent of the Terraform cell, but
the Terraform cell is what makes the hosting infrastructure exist.

---

### Proposed cell: `terraform` (or `colony-infra`)

**Suggested name:** `terraform`
**One-line purpose:** Manage the cloud infrastructure that hosts colony cells as networked
MCP servers.

**Copier invocation to spawn:**
```bash
uvx copier copy gh:JSBaxter/stem-cell terraform
# Answers:
#   project_name: terraform
#   project_purpose: Manage the cloud infrastructure that hosts colony cells as networked MCP servers.
#   language: python        (for the FastMCP control-plane server)
#   include_agent_container: true
#   include_bot_identity: true
#   github_remote: true
#   operator_github_handle: JSBaxter
#   colony_bot_login: jb-colony-bot[bot]
```

---

### What the cell would contain

```
terraform/
├── MANIFESTO.md, CONTRIBUTING.md, ...   # doc spine from stem-cell
├── src/
│   └── terraform/
│       └── server.py     # FastMCP MCP server: deploy/destroy/status tools
├── tf/
│   ├── modules/
│   │   ├── colony-base/  # VPC, container registry, shared networking
│   │   └── cell-service/ # per-cell: container + ingress + TLS
│   ├── environments/
│   │   ├── prod/
│   │   └── dev/
│   └── main.tf
├── dev-tools/             # queue, agent-bot, agent-container (from stem-cell)
└── tests/                 # pytest for the MCP server
```

**MCP tools the server would expose:**
| Tool | Description |
|------|-------------|
| `deploy_cell` | Run `terraform apply` for a named cell module |
| `destroy_cell` | Run `terraform destroy` for a named cell |
| `plan_cell` | Run `terraform plan` (dry-run, no mutations) |
| `list_deployed_cells` | Query Terraform state: which cells are live and where |
| `get_cell_endpoint` | Return the HTTPS URL for a deployed cell's MCP server |
| `health` | Check that the Terraform workspace and state backend are reachable |

**CI quality jobs to add:**
- `terraform fmt -check` — formatting gate
- `terraform validate` — schema + syntax check
- `tflint` — linting
- `checkov` — security scanning (optional but recommended)

---

### Cloud hosting options

Cells run as containers. The Terraform cell manages which cloud hosts them.

| Option | Terraform provider | Pros | Recommendation |
|--------|--------------------|------|----------------|
| **Google Cloud Run** | `hashicorp/google` | Auto-scaling, built-in HTTPS/DNS, simple TF, generous free tier, SSE works well | **Start here** |
| AWS ECS Fargate | `hashicorp/aws` | Mature ecosystem, strong IAM integration | Good if already on AWS |
| AWS Lambda + Function URL | `hashicorp/aws` | Cheapest for low traffic | Cold-start latency; avoid for persistent SSE connections |
| Fly.io | `fly-apps/fly` | Simple, global, cheap | Smaller Terraform ecosystem |
| Self-hosted Kubernetes | `hashicorp/kubernetes` | Full control | High operational burden for a colony |

**Recommended starting point:** Google Cloud Run. A single cell module looks like:
```hcl
resource "google_cloud_run_v2_service" "cell" {
  name     = var.cell_name
  location = var.region
  template {
    containers {
      image = "${var.registry}/${var.cell_name}:${var.image_tag}"
      ports { container_port = 8080 }
      env { name = "DATABASE_URL"; value_from { secret_key_ref { ... } } }
    }
  }
}
resource "google_cloud_run_v2_service_iam_member" "public" {
  service = google_cloud_run_v2_service.cell.name
  role    = "roles/run.invoker"
  member  = "allUsers"   # or restrict to colony bot SA
}
```

---

### How a deployed cell registers in atlas

After `terraform apply` provisions a cell's Cloud Run service, the post-deploy step would
call `mcp__atlas__register_cell` and `mcp__atlas__declare_capability` via the atlas MCP
server to record the cell's existence and endpoint:

```python
# Pseudo-code run by the terraform cell's MCP server post-deploy
atlas.register_cell(
    name="my-new-cell",
    repo_url="https://github.com/JSBaxter/my-new-cell",
    morphogen="terraform",   # induced_by the terraform cell
)
atlas.declare_capability(
    cell_name="my-new-cell",
    tag="mcp.hosted.cloud-run",
    endpoint="https://my-new-cell-xxxx.run.app/mcp/",
)
```

---

### Atlas registration for the terraform cell itself

Once the terraform cell is spawned, it should be registered here in atlas:

```python
# Via mcp__atlas__register_cell (can be done from here once the cell repo exists)
{
  "name": "terraform",
  "repo_url": "https://github.com/JSBaxter/terraform",
  "morphogen": "atlas"   # atlas cell prompted the creation
}
```

I have not pre-registered it because the cell does not yet exist and atlas enforces that
registered cells are real.

---

### What I am NOT able to do (CI constraint)

- **Scaffold the cell repo.** Requires `uvx copier copy gh:JSBaxter/stem-cell terraform` run
  by the operator with write access to create the GitHub repo.
- **Write Terraform code in a new repo.** Out of scope for this cell.
- **Deploy infrastructure.** No cloud credentials are available in this CI run.

---

### Recommended next steps for operator

1. **Spawn the cell:** `uvx copier copy gh:JSBaxter/stem-cell terraform` (answer as above)
2. **Create GitHub repo** `JSBaxter/terraform` with topic `colony-cell`
3. **Add the copier colony_bot_login, CLAUDE_CODE_OAUTH_TOKEN, COLONY_BOT_APP_ID,
   COLONY_BOT_PRIVATE_KEY secrets** (same pattern as this cell)
4. **File a `claude-build` issue** in the new repo asking the agent to implement:
   - Terraform modules (`tf/modules/colony-base/` and `tf/modules/cell-service/`)
   - FastMCP control-plane server (`src/terraform/server.py`) with the 6 tools above
   - CI quality jobs (fmt, validate, tflint)
5. **Configure state backend** (GCS bucket or S3 bucket) for Terraform state; add the
   backend credentials as repo secrets
6. **Register the new cell in atlas** by filing a `claude-build` issue here (or in the new
   cell) once the repo exists

---

## 2026-05-27 — Ceremony 1: Backlog grooming (PR #20 trigger)

**Trigger:** PR #20 merged; 20 mod 5 == 0.

**Note:** Ceremonies 2 (health check) and 3 (structural review) also fire on PR #20
(20 mod 10 == 0, 20 mod 20 == 0). They will run in the next post-merge cycles.

### Queue closures

All pre-existing tasks were stale relative to the merged work:

| Task ID     | Title                                              | Previous status | Action   |
|-------------|----------------------------------------------------|-----------------|----------|
| task_yhfoog | Smoke test: cell-build (issue #13)                 | blocked         | closed ✓ |
| task_7avu3w | Smoke test: official-action dispatch (2026-05-27)  | blocked         | closed ✓ |
| task_ss7pyq | implement atlas MCP server (issue #18) — duplicate | failed          | closed ✓ |
| task_ppb25a | implement atlas MCP server (issue #18)             | blocked         | closed ✓ |

Rationale:
- **task_yhfoog / task_7avu3w**: Smoke test issues (#13) are closed; PRs #14, #17, #19, #20
  all confirm the cell-build pipeline works end-to-end.
- **task_ss7pyq / task_ppb25a**: Both tracked the same work (atlas MCP server). PR #20 merged
  it successfully. task_ss7pyq was in `failed` state from a prior run; superseded by task_ppb25a
  which carried the completed implementation.

### Issue closures

- **Issue #18** ("feat: implement the atlas MCP server") — closed. Work landed in PR #20.

### Rescoring

No open tasks remain after closures. Queue is clean.

### New items scoped

None. No open `claude-build` issues after closing #18.

### Observations (not actionable this run)

- `STATE.md` contains a stale reference: "PR 4 wires the MCP server on top" in the SQLite
  repository section — implementation-phase language left over from drafting. Ceremony 2
  (health check) will address this.
- `CHANGELOG.md` was missing the PR #20 atlas MCP server entry. Fixed inline in this PR.
