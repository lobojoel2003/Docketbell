# Common tasks. Run `make help` for a list.

PYTHON ?= python
LANGS := -l es -l zh_Hans -l vi -l ko -l ru -l ar -l ht

.PHONY: help install test lint format messages demo screenshots docker run worker release

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install Docketbell with development tools
	$(PYTHON) -m pip install -e ".[dev]"

test: ## Run the test suite with coverage
	$(PYTHON) -m pytest --cov

lint: ## Check style and common mistakes
	ruff check .
	ruff format --check .

format: ## Fix style automatically
	ruff check --fix .
	ruff format .

messages: ## Extract translatable strings and compile catalogs (needs GNU gettext)
	cd docketbell && DEBUG=true $(PYTHON) ../manage.py makemessages $(LANGS) --no-location --no-obsolete
	cd docketbell && DEBUG=true $(PYTHON) ../manage.py compilemessages

run: ## Run the development server
	DEBUG=true $(PYTHON) manage.py migrate
	DEBUG=true $(PYTHON) manage.py runserver

worker: ## Run the reminder worker
	DEBUG=true $(PYTHON) manage.py run_worker

demo: ## Run a demo server with fictional data (deletes court data in the database!)
	$(PYTHON) scripts/demo_server.py --port 8001

screenshots: ## Refresh docs/images from a running demo server
	node scripts/screenshots.cjs http://127.0.0.1:8001 docs/images
	pngquant --force --skip-if-larger --ext .png --quality 80-95 docs/images/*.png || true

docker: ## Build the Docker image
	docker build -t docketbell:local .

release: ## Prepare a release: make release VERSION=1.1.0
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=1.1.0" && exit 1)
	$(PYTHON) scripts/release.py $(VERSION)
