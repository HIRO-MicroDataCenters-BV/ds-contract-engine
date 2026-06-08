# Contract Generator client (auto-generated)

This folder is intended to hold the auto-generated Python client SDK for the Contract Generator service. The SDK is regenerated from [`api/contract-generator/openapi.yaml`](../../api/contract-generator/openapi.yaml) using `openapi-generator-cli`.

## Regenerate

From the repository root:

```bash
./tools/generate-clients.sh contract-generator
```

This produces a `ds_contract_generator/` package under this folder.

## Usage (after generation)

```python
from ds_contract_generator import ApiClient, Configuration
from ds_contract_generator.api.contracts_api import ContractsApi

config = Configuration(host="http://localhost:8082")
client = ApiClient(config)
api = ContractsApi(client)
response = api.generate_contract(generate_contract_request={...})
print(response.token)
```

The client is not committed to the repository — it is regenerated on demand.
