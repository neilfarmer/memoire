SHELL := /bin/bash

.PHONY: deploy deploy-auto invalidate destroy test test-unit test-terraform test-all coverage security lint tui-build tui-test tui-lint tui-run tui-security

deploy:
	@source .env && cd terraform && terraform apply

deploy-auto:
	@source .env && cd terraform && terraform apply -auto-approve
	@$(MAKE) invalidate

invalidate:
	@DIST_ID=$$(cd terraform && terraform output -raw cloudfront_distribution_id) && \
	  aws cloudfront create-invalidation --distribution-id $$DIST_ID --paths "/*"

destroy:
	@source .env && cd terraform && terraform destroy

lint:
	ruff check lambda/ tests/
	djlint frontend/ --lint
	cd terraform && terraform fmt -check -recursive

test: test-unit test-terraform

test-unit:
	python -m pytest tests/unit/ -v --cov=lambda --cov-report=term-missing --cov-report=xml --cov-fail-under=80

test-terraform:
	cd terraform && terraform test

test-all: test-unit test-terraform

coverage:
	python -m pytest tests/unit/ -q --cov=lambda --cov-report=html --cov-report=term-missing
	@echo "HTML report: htmlcov/index.html"

security:
	@echo "--- Python SAST (bandit) ---"
	bandit -r lambda/ --severity-level medium --confidence-level medium
	@echo "--- Dependency CVEs (pip-audit) ---"
	pip-audit -r requirements-test.txt -f columns

# ---- TUI (Go) -------------------------------------------------------------

tui-build:
	cd tui && CGO_ENABLED=0 go build -o ../bin/memoire ./cmd/memoire

tui-test:
	cd tui && go test ./...

tui-lint:
	cd tui && go vet ./...

tui-run:
	cd tui && go run ./cmd/memoire

tui-security:
	@go install golang.org/x/vuln/cmd/govulncheck@latest
	cd tui && $$(go env GOPATH)/bin/govulncheck ./...

