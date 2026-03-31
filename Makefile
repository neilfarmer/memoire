SHELL := /bin/bash

.PHONY: deploy deploy-auto invalidate destroy test

deploy:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform apply'

deploy-auto:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform apply -auto-approve'
	./scripts/invalidate-cache.sh

invalidate:
	./scripts/invalidate-cache.sh

destroy:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform destroy'

test:
	TEST_PAT=$(TEST_PAT) python tests/test_api.py

test-deploy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py deploy

test-destroy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py destroy
