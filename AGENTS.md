# Repository Guidelines

## Project Structure & Module Organization
This repository now uses a modular package layout under `src/`. Prefer updating the real implementation modules in `scripts/` and `src/`.
- `src/api/` contains the FastAPI app, routes, schemas, dependencies, and service layer.
- `src/orchestration/` contains the LangGraph workflow, route maps, checkpointing, shared graph state, and ticket nodes.
- `src/workers/` contains the worker loop and claimed-run execution path.
- `src/tickets/` contains the ticket state machine and message-log logic.
- `src/agents/`, `src/triage/`, `src/llm/`, `src/rag/`, `src/memory/`, `src/evaluation/`, and `src/telemetry/` separate model logic, routing rules, retrieval, memory, and observability concerns.
- `src/bootstrap/container.py` wires runtime dependencies.
- `src/contracts/` stores shared enums, IDs, outputs, and protocols.
- `src/tools/` contains Gmail, policy-provider, null-client, and ticket-store adapters.
- `tests/` contains the pytest suite.
- `docs/` and `docs/specs/` contain design notes and implementation specs.
- `evals/` contains evaluation docs, fixtures, and baseline assets; `.artifacts/evals/` stores local evaluation outputs.

## Build, Test, and Development Commands
Use Python 3.10+ in a virtual environment.

- `python -m venv .venv`
- `.venv\\Scripts\\activate`
- `pip install -r requirements.txt`
- `python scripts/init_db.py` applies Alembic migrations.
- `python scripts/build_index.py` rebuilds the local Chroma knowledge index.
- `python serve_api.py` starts the FastAPI server.
- `python run_worker.py` starts the worker loop.
- `python run_worker.py --once` processes at most one queued run.
- `python run_poller.py` runs one Gmail poller batch.
- `python scripts/run_real_eval.py --samples-path tests/samples/eval/customer_support_eval.jsonl --report-path .artifacts/evals/real_eval_report.json` runs real-environment HTTP evaluation.
- `pytest -q` runs the test suite.

Operational note: `POST /tickets/{ticket_id}/run` is enqueue-only. A worker must be running to execute queued runs.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation. Use `snake_case` for functions, variables, modules, and files. Use `PascalCase` for classes and dataclasses. Keep shared contracts explicit and typed.

- Add type hints for new public functions and methods.
- Keep route/state/action enums in `src/contracts/` instead of scattering string literals.
- Keep orchestration concerns in `src/orchestration/` and ticket lifecycle logic in `src/tickets/`.
- Keep prompt templates in `src/prompts/*.txt` and load them through `src/prompts/loader.py`.
- Prefer extending the current package layout instead of reintroducing removed flat modules such as legacy `src/graph.py`, `src/nodes.py`, or monolithic `src/agents.py`.
- Reuse `ServiceContainer` and existing protocols for runtime dependencies instead of adding hard-coded globals.

## Testing Guidelines
An automated `pytest` suite is present under `tests/`.

- Add or update targeted tests for every behavioral change.
- Follow the existing test style: fake providers, temporary SQLite databases, and container overrides instead of real Gmail or production services.
- For workflow changes, cover the affected route selection, state transitions, lease behavior, API contracts, and trace/evaluation side effects.
- For configuration or script changes, add focused tests similar to `tests/test_config.py` and `tests/test_init_db.py` when possible.
- Run the most specific tests first, then broaden to `pytest -q` when the change spans multiple modules.
- For docs-only changes, test execution is optional.

## Commit & Pull Request Guidelines
Keep commit messages short, imperative, and specific, such as `Refresh README for worker architecture`.

PRs should include:

- a concise summary of the behavior or documentation change,
- affected paths and any migration or config impact,
- test results or manual verification notes,
- evaluation notes when routing, drafting, or QA behavior changes,
- screenshots only when diagrams or UI-like docs materially change.

## Security & Configuration Tips
- Never commit `.env`, `credentials.json`, `token.json`, database credentials, or real customer content.
- Required runtime settings include `MY_EMAIL` and `LLM_API_KEY`.
- Index building requires embedding configuration such as `EMBEDDING_API_URL` and `EMBEDDING_MODEL`.
- Database configuration can come from `DATABASE_URL` or the `POSTGRES_*` variables.
- `LANGSMITH_*` settings are optional.
- Treat `.artifacts/knowledge_db/` as local Chroma state unless a change explicitly requires rebuilding or replacing the knowledge index.
- Prefer `GMAIL_ENABLED=false` for local API or test work that does not need live Gmail access.
