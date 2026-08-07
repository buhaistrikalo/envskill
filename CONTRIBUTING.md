# Contributing

1. Fork the repository and create a focused branch.
2. Add tests for behavior changes.
3. Run `uv run python -m unittest discover -s tests -v`.
4. Run `uv run --with ruff ruff check .`.
5. Open a pull request describing the security impact and test plan.

Never add real credentials or copied `.env` files to tests, issues, commits, or pull requests.
