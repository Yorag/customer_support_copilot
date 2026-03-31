# Repository Guidelines

## Project Structure & Module Organization
`main.py` runs the LangGraph workflow once for local execution. `deploy_api.py` exposes the same workflow through FastAPI/LangServe. Core logic lives in `src/`: `graph.py` defines routing, `nodes.py` holds node behavior, `agents.py` wires LLM/RAG chains, `state.py` defines shared state, `prompts.py` stores prompt text, and `tools/GmailTools.py` wraps Gmail access. Knowledge assets live in `data/`, the local Chroma index lives in `db/`, and design documents belong in `docs/`.

## Build, Test, and Development Commands
Use Python 3.10+ in a virtual environment.

- `python -m venv .venv`
- `.venv\\Scripts\\activate`
- `pip install -r requirements.txt` installs runtime dependencies.
- `python create_index.py` rebuilds the local Chroma index from `data/agency.txt`.
- `python main.py` runs one batch email-processing pass.
- `python deploy_api.py` starts the API on `localhost:8000`.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation. Use `snake_case` for functions, variables, and module names; use `PascalCase` for classes like `Workflow` and `GmailToolsClass`. Keep prompt constants uppercase in `src/prompts.py`. Preserve the existing separation between graph orchestration, agent logic, prompts, and external tools. Add type hints for new public functions and keep state fields explicit rather than relying on ad hoc keys.

## Testing Guidelines
No automated test suite is checked in yet. For new work, add `pytest` tests under a top-level `tests/` directory using names like `test_graph_routes.py`. At minimum, cover route selection, Gmail filtering behavior, and structured output parsing. Before opening a PR, run `python main.py` against safe test data or mocks and note what was verified manually.

## Commit & Pull Request Guidelines
Recent history uses short imperative commit messages such as `Updated README` and `Updated prompts and naming`. Keep that style, but make messages more specific, for example: `Add technical issue clarification template`. PRs should include a clear summary, affected paths, config changes, manual test notes, and screenshots only when UI or diagrams change.

## Security & Configuration Tips
Do not commit `.env`, `credentials.json`, `token.json`, or real customer data. Required environment variables include `MY_EMAIL`, `GROQ_API_KEY`, and `GOOGLE_API_KEY`. Treat `db/` as local development state unless a change explicitly requires regenerating the index.
