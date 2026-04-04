SHELL := /bin/bash

.PHONY: deploy deploy-auto invalidate destroy test test-unit

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

test-unit:
	python -m pytest tests/unit/ -v

test:
	TEST_PAT=$(TEST_PAT) python tests/test_api.py

test-deploy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py deploy

test-destroy-content:
	TEST_PAT=$(TEST_PAT) python tests/content.py destroy
