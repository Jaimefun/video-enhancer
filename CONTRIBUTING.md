# Contributing

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/video-enhancer.git
cd video-enhancer
python -m venv .venv && source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install ruff mypy pytest pytest-asyncio httpx
cp .env.example .env
```

## Running tests

```bash
pytest tests/ -v
```

## Linting

```bash
ruff check app/
mypy app/ --ignore-missing-imports
```

## Submitting a PR

1. Fork → feature branch → PR against `main`
2. All CI checks must pass before merge
3. Include tests for new behaviour
