SHELL := /bin/bash

.PHONY: deploy deploy-auto invalidate destroy test test-unit

deploy:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform apply'

deploy-auto:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform apply -auto-approve'
	./scripts/invalidate-cache.sh

invalidate:
	./scripts/invalidate-cache.sh

destroy:
	@bash -c 'source scripts/load-env.sh && cd terraform && terraform destroy'

test-unit:
	python -m pytest tests/test_auth_handler.py tests/test_authorizer.py tests/test_image_crud.py -v

test:
	TEST_PAT=$(TEST_PAT) python tests/test_api.py

test-deploy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py deploy

test-destroy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py destroy
