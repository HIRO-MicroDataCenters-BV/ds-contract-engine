# examples/

Worked examples for using the Contract Engine sub-services.

| Example | Description |
|---|---|
| [`end-to-end.sh`](end-to-end.sh) | Mints a contract via the Generator and validates it via the Validator using the locked v1 payload. |

## Running the end-to-end example

```bash
# Terminal 1 — Generator
cd server/contract-generator
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__SIGNING_KEY_PATH="./local-ed25519.pem" \
DS__SIGNING_KEY_ID="hus.nextgen.hiro-develop.nl#key-1" \
DS__ENVIRONMENT="development" \
poetry run uvicorn app.main:app --reload --port 8082

# Terminal 2 — Validator
cd server/contract-validator
DS__NODE_ID="hus.nextgen.hiro-develop.nl" \
DS__JWKS_BASE_URL_TEMPLATE="http://localhost:8082" \
DS__ENVIRONMENT="development" \
poetry run uvicorn app.main:app --reload --port 8083

# Terminal 3 — run the example
./examples/end-to-end.sh
```

Expected output:

```json
{
  "allow": true,
  "reason": null,
  "jti": "...",
  "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4"
}
```
