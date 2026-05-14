# 👥 CONTRIBUTING — JARVIS v5.2

**Como contribuir com o projeto**

---

## 🤝 CÓDIGO DE CONDUTA

- Seja respeitoso
- Colabore de forma construtiva
- Forneça feedback útil
- Responsabilize-se por seu código

---

## 🚀 COMEÇANDO

### 1. Fork & Clone

```bash
# Fork no GitHub (botão no canto superior direito)

# Clone seu fork
git clone https://github.com/SEU_USUARIO/JARVIS.git
cd JARVIS

# Add upstream
git remote add upstream https://github.com/ORIGINAL/JARVIS.git
```

### 2. Setup Local

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Start Ollama (separate terminal)
ollama serve

# Configure environment
cp backend/.env.example backend/.env
```

### 3. Create Feature Branch

```bash
# Update from upstream
git fetch upstream
git rebase upstream/main

# Create branch
git checkout -b feature/your-feature-name

# Conventional branch names:
# feature/  — new feature
# fix/      — bug fix
# docs/     — documentation
# perf/     — performance
# refactor/ — code refactoring
# test/     — tests
```

---

## 💻 DESENVOLVIMENTO

### Code Style

**We use:**
- Black (formatting)
- isort (import sorting)
- Pylint (linting)
- MyPy (type checking)

**Before commit:**
```bash
# Format
black backend/ tests/

# Sort imports
isort backend/ tests/

# Lint
flake8 backend/ --max-line-length=120

# Type check
mypy backend/ --ignore-missing-imports

# Security scan
bandit -r backend/

# Tests
pytest tests/ -v
```

### File Organization

```
backend/
├── routes/         → HTTP endpoints (keep thin)
├── core/           → Business logic
├── services/       → External integrations
├── actions/        → Tools/actions
├── middleware/     → FastAPI middleware
└── ...
```

### Naming Conventions

```python
# Constants: UPPER_CASE
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Functions/variables: snake_case
async def process_message(msg: str) -> str:
    pass

# Classes: PascalCase
class MessageProcessor:
    pass

# Private: _leading_underscore
def _internal_helper():
    pass

# Constants in classes: UPPER_CASE
class Config:
    MAX_SIZE = 1000
```

### Docstrings

**Use short docstrings for simple functions:**
```python
def process_input(text: str) -> str:
    """Process and validate user input."""
    return text.strip()
```

**Use detailed docstrings for complex logic:**
```python
async def orchestrate_request(message: str, session_id: str) -> dict:
    """
    Route message through intent classifier and execute appropriate action.
    
    Args:
        message: User input message
        session_id: Unique session identifier
        
    Returns:
        Response dict with status and result
        
    Raises:
        ValueError: If message is empty
        RuntimeError: If no handler found
    """
    pass
```

### Type Hints

**Use type hints everywhere:**
```python
from typing import Optional, List, Dict

def get_user(user_id: int) -> Optional[User]:
    pass

def process_batch(items: List[str]) -> Dict[str, int]:
    pass

async def fetch_data(url: str) -> dict:
    pass
```

---

## 🧪 TESTING

### Test Structure

```python
# tests/test_feature.py
import pytest
from fastapi.testclient import TestClient

class TestFeatureName:
    """Test suite for feature."""
    
    def test_happy_path(self, client: TestClient):
        """Test normal operation."""
        response = client.post("/endpoint", json={"data": "test"})
        assert response.status_code == 200
    
    def test_error_case(self, client: TestClient):
        """Test error handling."""
        response = client.post("/endpoint", json={})
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async code."""
        result = await async_function()
        assert result is not None
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_feature.py::TestFeatureName::test_happy_path -v

# With coverage
pytest tests/ --cov=backend --cov-report=html

# Specific markers
pytest -m asyncio tests/
pytest -m not slow tests/  # Skip slow tests
```

### Coverage Requirements

- Minimum: 70% overall
- Critical paths: 100%
- Actions: 80%+
- Middleware: 90%+

---

## 🔄 GIT WORKFLOW

### Commits

**Use conventional commits:**
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Examples:**
```
feat(chat): add sentiment analysis to responses

fix(security): prevent path traversal in file operations

docs(api): update endpoint documentation

test(actions): add comprehensive action tests

refactor(core): simplify orchestrator logic
```

### Commit Best Practices

- ✅ Small, focused commits
- ✅ One feature per commit
- ✅ Descriptive messages
- ✅ Reference issues: `Fixes #123`

**DON'T:**
- ❌ Mix formatting with logic
- ❌ Huge commits (100+ files)
- ❌ Non-descriptive messages ("fix bug")
- ❌ Commit commented-out code

### Push & Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create PR on GitHub
# Title: feat: add sentiment analysis
# Description: 
# - What: Implemented sentiment analysis
# - Why: Better user understanding
# - How: Using transformers library
# - Tests: Added 15 tests with 90% coverage

# Link issue: Closes #123
```

### PR Requirements

- [ ] Tests added (70%+ coverage)
- [ ] Documentation updated
- [ ] Code formatted (black)
- [ ] All checks passing
- [ ] No merge conflicts
- [ ] Reviewed by 1+ maintainer

---

## 📚 DOCUMENTATION

### Update README.md

- Feature summary
- Usage example
- Configuration options
- Performance characteristics

### Update ARCHITECTURE.md

- Design decisions
- Component interactions
- Data flow changes

### Create CHANGELOG entry

- What changed
- Why it changed
- Breaking changes (if any)

---

## 🔒 SECURITY

### Never commit:

- ❌ API keys
- ❌ Passwords
- ❌ Private tokens
- ❌ Secrets

### Use environment variables:

```python
# ✅ GOOD
api_key = os.environ.get("ANTHROPIC_KEY")

# ❌ BAD
api_key = "sk-..."  # Never hardcode!
```

### Validate user input:

```python
# ✅ GOOD
@router.post("/execute")
async def execute(cmd: str):
    if not cmd.strip():
        raise ValueError("Empty command")
    
    # Whitelist
    if any(dangerous in cmd for dangerous in ["rm -rf", "sudo"]):
        raise SecurityError("Dangerous command blocked")
    
    return await shell_exec(cmd)

# ❌ BAD
@router.post("/execute")
async def execute(cmd: str):
    return os.system(cmd)  # Command injection!
```

---

## 🎯 WHAT TO WORK ON

### Good for beginners:
- [ ] Documentation improvements
- [ ] Adding tests
- [ ] Fixing typos
- [ ] Simple bug fixes
- [ ] Code formatting

### Good for intermediate:
- [ ] New actions (tools)
- [ ] Performance improvements
- [ ] Error handling
- [ ] Logging enhancements

### Good for advanced:
- [ ] New agents
- [ ] Architecture changes
- [ ] Complex features
- [ ] Infrastructure improvements

### Areas that need help:
1. **Documentation** — Always needed
2. **Tests** — Increase coverage
3. **Actions** — More integrations
4. **Optimization** — Reduce latency
5. **Accessibility** — Mobile support

---

## 📝 COMMIT CHECKLIST

Before pushing, ensure:

- [ ] Code formatted: `black backend/`
- [ ] Imports sorted: `isort backend/`
- [ ] Lints pass: `flake8 backend/`
- [ ] Types valid: `mypy backend/`
- [ ] Security OK: `bandit -r backend/`
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Coverage ≥70%: `pytest --cov`
- [ ] No secrets in code
- [ ] Docstrings added
- [ ] Related docs updated

---

## 🚫 CI/CD

All PRs must pass:
- ✅ Tests (pytest)
- ✅ Linting (black, flake8, pylint)
- ✅ Type checking (mypy)
- ✅ Security (bandit, safety)
- ✅ Build check (imports)

---

## 🤔 NEED HELP?

- **Questions:** Open a Discussion
- **Bugs:** Open an Issue with reproduction steps
- **Ideas:** Start a Discussion first
- **Chat:** Join our Discord (if applicable)

---

## 🎉 THANK YOU!

Every contribution helps make JARVIS better! 

---

**Last Updated:** 2026-05-13  
**Maintainer:** JARVIS Team
