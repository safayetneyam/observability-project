.PHONY: help env up down ps logs k8s k8s-down verify demo chaos dashboards zip clean

help:            ## show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env:             ## create .env from the example (edit it afterwards!)
	@test -f .env || (cp .env.example .env && chmod 600 .env && echo "created .env - edit SMTP + password")

up:              ## build and start the Compose stack
	docker compose up -d --build
	docker compose ps

up-mailpit:      ## start the stack plus the local Mailpit test inbox
	docker compose --profile mailpit up -d --build

down:            ## stop the stack (keeps volumes)
	docker compose --profile mailpit down

ps:              ## show services
	docker compose ps

logs:            ## follow app logs
	docker compose logs -f app

k8s:             ## deploy MicroK8s workloads + Alloy
	./scripts/deploy-k8s.sh

k8s-down:        ## remove MicroK8s workloads + Alloy
	-microk8s helm3 uninstall alloy -n monitoring
	-microk8s kubectl delete -f kubernetes/workload.yaml
	-microk8s kubectl delete -f kubernetes/namespace.yaml

verify:          ## run end-to-end checks and save evidence/verification-*.txt
	./scripts/verify.sh

demo:            ## normal → burst → failures, with before/after metrics
	./scripts/traffic-test.sh demo

chaos:           ## fire the high-error-rate alert (50% 503s for 4 min)
	./scripts/traffic-test.sh chaos 0.5 240

dashboards:      ## regenerate grafana/dashboards/*.json
	python3 scripts/generate-dashboards.py

zip:             ## package for submission (excludes .env and raw data)
	cd .. && zip -r $(notdir $(CURDIR))_observability.zip $(notdir $(CURDIR)) -x '*/.env' '*/__pycache__/*' '*.db' '*/evidence/raw/*' '*.pdf'

clean: down k8s-down  ## remove everything INCLUDING data volumes
	docker compose --profile mailpit down -v
