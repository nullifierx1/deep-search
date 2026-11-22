.SILENT: cli gui api run clean clean-cache-results pep8 test format install help check

PYTHON = python3
FLAKE8 = flake8
MYPY = mypy
FORMATTER = black
PYTEST = pytest
PACKAGE = python_deep_search
TEST_DIR = tests

QUERY ?=
REGEX ?=\b\w+\b
SITES ?=python_deep_search/json-sites-examples/sites.json
FOLLOW_LIMIT ?=5
MAX_RESULTS ?=10
TIMEOUT ?=15
WORKERS ?=6
OUT ?=python_deep_search/results.json
VERBOSE ?=0
API_PORT ?=8765

.PHONY: cli gui api run clean clean-cache-results pep8 test format install help check all

cli:
	@if not defined QUERY (echo Usage: make cli QUERY="search query" [REGEX="..." SITES="..." ...] && exit /b 1)
	@if "$(VERBOSE)"=="1" ($(PYTHON) -m $(PACKAGE).main --mode cli $(QUERY) --regex "$(REGEX)" --sites "$(SITES)" --follow-limit $(FOLLOW_LIMIT) --max-results $(MAX_RESULTS) --timeout $(TIMEOUT) --workers $(WORKERS) --out "$(OUT)" --verbose) else ($(PYTHON) -m $(PACKAGE).main --mode cli $(QUERY) --regex "$(REGEX)" --sites "$(SITES)" --follow-limit $(FOLLOW_LIMIT) --max-results $(MAX_RESULTS) --timeout $(TIMEOUT) --workers $(WORKERS) --out "$(OUT)")

cli-no-follow:
	@if not defined QUERY (echo Usage: make cli-no-follow QUERY="search query" && exit /b 1)
	$(PYTHON) -m $(PACKAGE).main --mode cli $(QUERY) --regex "$(REGEX)" --sites "$(SITES)" --follow-limit $(FOLLOW_LIMIT) --max-results $(MAX_RESULTS) --timeout $(TIMEOUT) --workers $(WORKERS) --no-follow --out "$(OUT)"

cli-no-playwright:
	@if not defined QUERY (echo Usage: make cli-no-playwright QUERY="search query" && exit /b 1)
	$(PYTHON) -m $(PACKAGE).main --mode cli $(QUERY) --regex "$(REGEX)" --sites "$(SITES)" --follow-limit $(FOLLOW_LIMIT) --max-results $(MAX_RESULTS) --timeout $(TIMEOUT) --workers $(WORKERS) --no-playwright --out "$(OUT)"

cli-open:
	@if not defined QUERY (echo Usage: make cli-open QUERY="search query" && exit /b 1)
	$(PYTHON) -m $(PACKAGE).main --mode cli $(QUERY) --regex "$(REGEX)" --sites "$(SITES)" --follow-limit $(FOLLOW_LIMIT) --max-results $(MAX_RESULTS) --timeout $(TIMEOUT) --workers $(WORKERS) --open --out "$(OUT)"

gui:
	$(PYTHON) -m $(PACKAGE).main --mode gui

api:
	$(PYTHON) -m $(PACKAGE).api --port $(API_PORT)

run: cli

clean:
	@echo Cleaning temporary files...
	-for /d /r . %d in (__pycache__) do @if exist "%d" rmdir /s /q "%d"
	-del /q *.pyc 2>nul
	-del /q *.pyo 2>nul
	-if exist .pytest_cache rmdir /s /q .pytest_cache
	-if exist .mypy_cache rmdir /s /q .mypy_cache
	-if exist .coverage del /q .coverage
	-if exist htmlcov rmdir /s /q htmlcov
	@echo Clean completed!

clean-cache-results:
	@echo Cleaning search result cache...
	-if exist python_deep_search\.cache\results_cache.json del /q python_deep_search\.cache\results_cache.json
	@echo Search result cache cleaned. Settings were not changed.

pep8:
	@echo Checking PEP8...
	$(FLAKE8) $(PACKAGE) --max-line-length=120 --ignore=E203,W503
	@echo PEP8 check completed!

format:
	@echo Formatting code with $(FORMATTER)...
	-$(FORMATTER) $(PACKAGE)

test:
	@echo Running tests...
	-$(PYTEST) -v --cov=$(PACKAGE) --cov-report=html
	@echo Tests completed!

install:
	@echo Installing dependencies...
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install flake8 black mypy pytest pytest-cov requests
	@echo Dependencies installed!

install-req:
	@echo Installing from requirements.txt...
	-if exist requirements.txt ($(PYTHON) -m pip install -r requirements.txt) else (echo requirements.txt not found)

venv:
	@echo Creating virtual environment...
	$(PYTHON) -m venv .venv
	@echo Virtual environment created!
	@echo To activate:
	@echo   .venv\Scripts\activate  (Windows)
	@echo   source .venv/bin/activate  (Linux/Mac)

check: pep8
	@echo Running mypy...
	-$(MYPY) $(PACKAGE) --ignore-missing-imports
	@echo All checks completed!

all: clean check test
	@echo All tasks completed!

help:
	@echo ===== Deep Search Makefile =====
	@echo.
	@echo   Application:
	@echo     make gui                       Launch GUI
	@echo     make api API_PORT=8765         Launch localhost API
	@echo     make cli QUERY="query"          CLI search
	@echo     make cli-open QUERY="query"     CLI + open links in browser
	@echo     make cli-no-follow QUERY="..."  CLI without following links
	@echo     make cli-no-playwright QUERY=".." CLI without Playwright
	@echo.
	@echo   CLI options (override with VAR=value):
	@echo     REGEX="\bregex\b"    SITES="sites.json"   FOLLOW_LIMIT=5
	@echo     MAX_RESULTS=10       TIMEOUT=15            WORKERS=6
	@echo     OUT="results.json"   VERBOSE=1
	@echo.
	@echo   Development:
	@echo     make run             Run CLI (alias for make cli)
	@echo     make clean           Remove temp files
	@echo     make clean-cache-results Remove query/result cache only
	@echo     make pep8            Check PEP8 ($(PACKAGE)
	@echo     make format          Format with black
	@echo     make test            Run tests with coverage
	@echo     make install         Install dev dependencies
	@echo     make install-req     Install from requirements.txt
	@echo     make venv            Create virtualenv
	@echo     make check           pep8 + mypy
	@echo     make all             clean + check + test
	@echo     make help            Show this help
