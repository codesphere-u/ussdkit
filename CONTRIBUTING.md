# Contributing to `ussdkit`

1. Fork the repository and create a feature branch (`git checkout -b feat/my-change`).
2. Install dev dependencies: `uv sync --extra dev`.
3. Ensure `uv run pytest -v`, `uv run ruff check src tests examples`, and `uv run mypy src` all pass cleanly.
4. Open a pull request with clear reproduction steps and test coverage.
