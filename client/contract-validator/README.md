# Contract Validator client (auto-generated)

This folder is intended to hold the auto-generated Python client SDK for the Contract Validator service. The SDK is regenerated from [`api/contract-validator/openapi.yaml`](../../api/contract-validator/openapi.yaml) using `openapi-generator-cli`.

## Regenerate

From the repository root:

```bash
./tools/generate-clients.sh contract-validator
```

This produces a `ds_contract_validator/` package under this folder.

## Usage (after generation)

```python
from ds_contract_validator import ApiClient, Configuration
from ds_contract_validator.api.validation_api import ValidationApi

config = Configuration(host="http://localhost:8083")
client = ApiClient(config)
api = ValidationApi(client)
response = api.validate_contract(validate_request={"token": "<JWT>"})
print(response.allow)
```

The client is not committed to the repository — it is regenerated on demand.
