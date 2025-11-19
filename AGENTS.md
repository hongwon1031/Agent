# Repository Guidelines

## Project Structure & Modules
- Core entry point: `main.py` orchestrates reading data, running parsing agents, and writing results.
- Parsing logic lives in agent modules such as `Condition_Parsing_Agent.py`, `Definition_Parsing_Agent.py`, `Title_1.py`, `Title_3.py`, and `semantic_parsing.py`.
- Shared utilities and data shaping are in `document_context_builder.py`, `schema_mapper.py`, `structure.py`, and the `data/`, `Tree/`, and `results/` directories.
- Configuration and input artifacts include `.env`, `concepts.json`, `result.json`, and files under `data/`.

## Build, Test, and Development
- Use Python 3.10+ and a virtual environment (`python -m venv .venv` then `.\.venv\Scripts\activate` on Windows).
- Install dependencies (if a requirements file exists): `pip install -r requirements.txt`.
- Run the main pipeline: `python main.py`. Optionally pass or adjust inputs via `.env`, `data/`, or `concepts.json`.
- For ad‑hoc checks of individual agents, run them directly, e.g. `python Condition_Parsing_Agent.py`.

## Coding Style & Naming
- Use 4‑space indentation and keep lines under ~100 characters.
- Prefer descriptive names: `parse_condition_block`, `build_document_context`, etc.; avoid single letters outside short loops.
- New modules should use `snake_case` file names (e.g. `new_parsing_agent.py`) and follow existing patterns in the related files.

## Testing Guidelines
- Add lightweight, script‑style tests near the behavior you change (e.g. `if __name__ == "__main__":` blocks or small helper scripts under `tests/` if added).
- Test typical, edge, and failure cases by running `python main.py` on representative samples in `data/` and verifying outputs in `results/`.

## Commit & Pull Request Guidelines
- Write clear, imperative commit messages: `Add title parsing for section 3`, `Refactor schema mapper`, etc.
- Keep changes focused (one logical change per PR) and describe intent, approach, and any behavioral impact.
- Reference related issues or tasks, and include sample input/output snippets or paths under `results/` when behavior changes.
