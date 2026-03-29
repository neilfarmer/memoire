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
	source .env && python tests/test_api.py
