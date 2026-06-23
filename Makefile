.PHONY: deploy deploy-gpu update start stop dev build seed logs down reset

# ── Production (default) ──────────────────────────────────────────
deploy:
	@bash deploy.sh

deploy-gpu:
	@bash deploy.sh --gpu nvidia

deploy-amd:
	@bash deploy.sh --gpu amd

deploy-intel:
	@bash deploy.sh --gpu intel

deploy-cpu:
	@bash deploy.sh --gpu cpu

update:
	@bash deploy.sh --update

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-reset:
	docker compose -f docker-compose.prod.yml down -v
	@echo "All volumes wiped. Run 'make deploy' for a fresh deployment."

# ── Development ───────────────────────────────────────────────────
start:
	@bash start.sh

stop:
	@bash stop.sh

dev:
	docker compose -f docker-compose.dev.yml up --build

build:
	docker compose -f docker-compose.dev.yml build

seed:
	docker compose -f docker-compose.dev.yml exec backend python seed.py

logs:
	docker compose -f docker-compose.dev.yml logs -f backend

down:
	docker compose -f docker-compose.dev.yml down

reset:
	docker compose -f docker-compose.dev.yml down -v
