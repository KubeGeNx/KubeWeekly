.DEFAULT_GOAL := help

IMAGE      ?= vasudevdchavan/kubeweekly
TAG        ?= latest
NAMESPACE  ?= kubeweekly
SECRET_FILE ?= deploy/k8s/secret.local.yaml
ENV_FILE   ?= $(HOME)/.env
MINIKUBE_PROFILE ?= homelab

.PHONY: help build push deploy diff set-image release undeploy \
        secret sync-secret minikube-load local-deploy \
        trigger logs status venv test dry-run run clean

help: ## Show this help
	@echo "KubeWeekly deployment targets:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Override IMAGE, TAG, or NAMESPACE, e.g.: make deploy NAMESPACE=kubeweekly-staging"

build: ## Build the container image (IMAGE:TAG)
	docker build -f deploy/Dockerfile -t $(IMAGE):$(TAG) .

push: build ## Build and push the container image
	docker push $(IMAGE):$(TAG)

deploy: ## Apply namespace, PVC, ConfigMap (from config/sources.yaml), and CronJob
	kubectl apply -k .

diff: ## Show what `make deploy` would change, without applying it
	kubectl diff -k . || true

set-image: ## Point the CronJob at IMAGE:TAG without re-applying the rest
	kubectl set image cronjob/kubeweekly-daily kubeweekly=$(IMAGE):$(TAG) -n $(NAMESPACE)
	@# kubectl set image only patches .image, not .imagePullPolicy - k8s defaults the
	@# latter to Always the first time a :latest tag is applied, and it then sticks even
	@# after switching to a local tag, causing ImagePullBackOff against a nonexistent
	@# registry repo. Force it explicitly: Always for :latest, IfNotPresent otherwise.
	kubectl patch cronjob kubeweekly-daily -n $(NAMESPACE) --type=json -p='[{"op":"replace","path":"/spec/jobTemplate/spec/template/spec/containers/0/imagePullPolicy","value":"$(if $(filter latest,$(TAG)),Always,IfNotPresent)"}]'

release: push deploy set-image ## Build, push, deploy manifests, and point the CronJob at the new image

undeploy: ## Delete everything `make deploy` created (namespace, PVC, CronJob, ConfigMap) - also deletes the PVC's data. Does NOT delete the Secret.
	kubectl delete -k . --ignore-not-found

secret: ## Apply the real Secret from $(SECRET_FILE) (copy deploy/k8s/secret.example.yaml there first and fill in real values - never commit it)
	@test -f $(SECRET_FILE) || { \
		echo "Missing $(SECRET_FILE)."; \
		echo "Copy deploy/k8s/secret.example.yaml to $(SECRET_FILE), fill in real values, then re-run 'make secret'."; \
		exit 1; \
	}
	kubectl apply -f $(SECRET_FILE)

sync-secret: ## Regenerate $(SECRET_FILE) from values in $(ENV_FILE) (never prints the values)
	python3 scripts/sync_secret.py $(ENV_FILE) deploy/k8s/secret.example.yaml $(SECRET_FILE)

minikube-load: build ## Build IMAGE:TAG and load it into a local minikube profile (no registry push needed)
	minikube image load $(IMAGE):$(TAG) -p $(MINIKUBE_PROFILE)

local-deploy: minikube-load deploy set-image sync-secret secret ## One-shot local path: build, load into minikube, deploy manifests, point CronJob at the local image, sync+apply the secret from $(ENV_FILE)

trigger: ## Manually trigger one CronJob run, for smoke-testing a deploy
	kubectl create job --from=cronjob/kubeweekly-daily kubeweekly-manual-$(shell date +%s) -n $(NAMESPACE)

logs: ## Tail logs from the most recently created kubeweekly pod
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l app=kubeweekly --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}'); \
	if [ -z "$$POD" ]; then echo "No kubeweekly pods found in namespace $(NAMESPACE)."; exit 1; fi; \
	echo "Tailing $$POD ..."; \
	kubectl logs -n $(NAMESPACE) -f $$POD

status: ## Show CronJob, Jobs, and Pod status
	kubectl get cronjob,jobs,pods -n $(NAMESPACE) -l app=kubeweekly

venv: ## Create local virtualenv and install dev dependencies
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt

test: venv ## Run the test suite locally
	.venv/bin/python -m pytest -q

dry-run: venv ## Run the pipeline locally against a small source subset (requires the API key matching LLM_PROVIDER, see ~/.env)
	PYTHONPATH=src .venv/bin/python -m kubeweekly.main --dry-run

run: venv ## Run the full pipeline locally against all of config/sources.yaml (writes to data/)
	PYTHONPATH=src .venv/bin/python -m kubeweekly.main

clean: ## Remove local venv and test caches
	rm -rf .venv .pytest_cache
