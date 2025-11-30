# AGENTS.md

## Build & Run Commands
- **Run app**: `python -m app.main` (from webapp directory)
- **Install deps**: `pip install -r requirements.txt`
- **Run tests**: `pytest` or `pytest path/to/test.py::test_function` for single test
- **Docker**: `docker-compose up -d`

## Code Style Guidelines
- **Imports**: Standard library, third-party, then relative imports (e.g., `from ..models.user import User`)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- **Types**: Use type hints everywhere. Prefer `str | None` over `Optional[str]` (Python 3.10+)
- **Models**: Use SQLAlchemy 2.0 `Mapped[]` annotations

## Error Handling
- Use custom exceptions inheriting from base classes (see `app/auth.py`)
- Log errors with `logger.error(f"Message: {e}")` before re-raising
- Return `tuple[bool, str]` for validation functions

## Documentation
- Google-style docstrings with Args/Returns/Raises sections
- Module-level docstrings describing purpose

## Architecture
- Layered: models -> services -> UI (NiceGUI)
- Use DTOs for passing data outside SQLAlchemy sessions
- Singleton pattern for managers via `get_*()` functions
