# AI Gateway — developer shortcuts (Azure-only)

.PHONY: test lint format deploy

## Run the test suite. Raw-SQL suites (identity, admin) use testcontainers and
## need a running Docker daemon; the rest run without it.
test:
	pytest services/ -v

## Lint + format check
lint:
	ruff check services/
	ruff format --check services/

## Apply formatting
format:
	ruff format services/

## Deploy the gateway to the Dev environment (Azure Container Apps).
## Requires `az login` with access to the PlatformAITooling Dev subscription.
deploy:
	az deployment group create \
	  --resource-group rg-aigw-dev-sdc \
	  --template-file infra/bicep/environments/dev/main.bicep \
	  --parameters infra/bicep/environments/dev/main.bicepparam
