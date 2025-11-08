# StarMoney Python SDK

Official async Python client for the StarMoney Bank API.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- **🚀 Async-first**: Built with `httpx` for modern async/await patterns
- **🔐 Secure**: Automatic JWT authentication and HMAC webhook validation
- **💰 Simple**: Send a payment in < 20 lines of code
- **🎯 Type-safe**: Full type hints for IDE autocomplete
- **📦 Lightweight**: Minimal dependencies, focused scope

## 📦 Installation

```bash
pip install starmoney-python
```

## 🚀 Quick Start

### Send a Payment (Complete Flow)

```python
import asyncio
from starmoney import StarmoneyClient

async def main():
    async with StarmoneyClient(
        jwt_secret="your-jwt-secret",
        issuer="your-service-name",
        base_url="https://api.starmoney.com/v1"
    ) as client:
        # 1. Create account
        account = await client.accounts.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone_number="+1234567890",
            document_type="PASSPORT",
            document_number="AB123456",
            address="123 Main St"
        )
        user_id = account["user_id"]

        # 2. Link payment rail
        await client.accounts.link_rail(user_id, rail_name="BDK")

        # 3. Send payment
        payment = await client.payments.send(
            user_id=user_id,
            amount=100.00,
            currency="EUR",
            beneficiary_iban="FR1420041010050500013M02606",
            beneficiary_name="Jane Smith",
            description="Test payment"
        )

        # 4. Check status
        status = await client.payments.get_status(
            user_id=user_id,
            client_transaction_id=payment["client_transaction_id"]
        )

        print(f"Payment status: {status['status']}")

asyncio.run(main())
```

## 🔐 Authentication

### Get Your Credentials

1. **JWT Secret**: Contact StarMoney to register your service and receive JWT credentials
2. **Issuer**: Your service identifier (e.g., `"your-company-name"`)

### Configuration

```python
from starmoney import StarmoneyClient

client = StarmoneyClient(
    jwt_secret="your-jwt-secret-here",
    issuer="your-service-name",
    base_url="https://api.starmoney.com/v1",  # Production
    # base_url="http://localhost:8000/starmoney/v1"  # Local development
    timeout=30
)
```

## 💳 Core Operations

### Accounts

```python
# Create account
account = await client.accounts.create(
    first_name="John",
    last_name="Doe",
    email="john@example.com",
    phone_number="+1234567890",
    document_type="PASSPORT",
    document_number="AB123456",
    address="123 Main St"
)

# Link payment rail
await client.accounts.link_rail(user_id, rail_name="BDK")
```

### Beneficiaries

```python
# Create beneficiary
beneficiary = await client.beneficiaries.create(
    user_id=user_id,
    name="Jane Smith",
    iban="FR1420041010050500013M02606",
    currency="EUR",
    bank_name="Test Bank",
    address="456 Test Ave"
)

# List beneficiaries
beneficiaries = await client.beneficiaries.list(user_id=user_id)
```

### Payments

```python
# Send payment (client_transaction_id auto-generated for idempotency)
payment = await client.payments.send(
    user_id=user_id,
    amount=100.00,
    currency="EUR",
    beneficiary_iban="FR1420041010050500013M02606",
    beneficiary_name="Jane Smith",
    description="Invoice #12345"
)

# Check payment status
status = await client.payments.get_status(
    user_id=user_id,
    client_transaction_id=payment["client_transaction_id"]
)

# Payment status can be:
# - PENDING: Initial state
# - PROCESSING: Being processed by payment rail
# - ACCEPTED: Accepted by payment rail
# - COMPLETED: Successfully completed
# - FAILED: Permanent failure
```

## 📡 Webhooks

### Subscribe to Events

```python
# Subscribe to payment events
result = await client.webhooks.batch_subscribe(
    endpoint_url="https://yourapp.com/webhooks/starmoney",
    webhook_secret="your-webhook-secret",
    event_subscriptions=[
        {"event_type": "payment.initiated", "subscribed_users": None},
        {"event_type": "payment.completed", "subscribed_users": None},
        {"event_type": "payment.failed", "subscribed_users": None},
    ],
    retry_attempts=3,
    timeout_seconds=10
)
```

### Validate Webhook Signatures (CRITICAL!)

```python
from fastapi import FastAPI, Request, HTTPException
from starmoney.webhooks import WebhookValidator

app = FastAPI()
validator = WebhookValidator(webhook_secret="your-webhook-secret")

@app.post("/webhooks/starmoney")
async def handle_webhook(request: Request):
    # Get raw payload and signature
    payload = await request.body()
    signature = request.headers.get("X-Webhook-Signature")

    # Validate signature (prevents spoofed webhooks)
    try:
        event = validator.parse_webhook(payload, signature)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Process webhook
    event_type = event["event_type"]
    event_data = event["data"]

    if event_type == "payment.completed":
        # Handle successful payment
        print(f"Payment completed: {event_data['transaction_id']}")

    return {"status": "received"}
```

## 🔧 Advanced Usage

### Idempotency

SDK automatically generates `client_transaction_id` for safe retries:

```python
# Automatic idempotency key
payment1 = await client.payments.send(user_id=user_id, amount=100, ...)
# client_transaction_id = "sdk-<uuid>"

# Or provide your own
payment2 = await client.payments.send(
    user_id=user_id,
    amount=100,
    client_transaction_id="order-12345",  # Your own idempotency key
    ...
)
```

### Error Handling

```python
from starmoney import (
    ValidationError,
    PaymentNotFoundError,
    DuplicateResourceError,
    AuthenticationError,
    ServerError
)

try:
    payment = await client.payments.send(...)
except ValidationError as e:
    print(f"Invalid payment data: {e.message}")
except DuplicateResourceError as e:
    print(f"Payment already exists: {e.message}")
except AuthenticationError as e:
    print(f"Authentication failed: {e.message}")
except ServerError as e:
    print(f"Server error: {e.message}")
```

### Context Manager vs Manual Close

```python
# Recommended: Use async context manager
async with StarmoneyClient(...) as client:
    await client.payments.send(...)
# Automatically closes connections

# Or manually manage lifecycle
client = StarmoneyClient(...)
try:
    await client.payments.send(...)
finally:
    await client.close()
```

## 📖 Examples

See the [`examples/`](examples/) directory for complete examples:

- [`quickstart.py`](examples/quickstart.py) - Complete payment flow
- [`webhook_handler.py`](examples/webhook_handler.py) - Webhook receiver with signature validation

## 🔍 API Reference

### StarmoneyClient

Main client class for interacting with StarMoney API.

**Constructor Arguments:**
- `jwt_secret` (str): JWT secret key for authentication
- `issuer` (str): Issuer identifier (default: "starmoney-sdk")
- `base_url` (str): API base URL (default: "http://localhost:8000/starmoney/v1")
- `timeout` (int): Request timeout in seconds (default: 30)

**Resources:**
- `client.accounts` - Account management
- `client.beneficiaries` - Beneficiary management
- `client.payments` - Payment operations
- `client.webhooks` - Webhook subscriptions

### WebhookValidator

Validates HMAC-SHA256 signatures on incoming webhooks.

**Methods:**
- `verify_signature(payload: bytes, signature_header: str) -> bool`
- `parse_webhook(payload: bytes, signature_header: str) -> dict`

## 🛠️ Development

### Setup

```bash
cd sdk/
poetry install
```

### Run Examples

```bash
# Make sure StarMoney API is running on localhost:8000
poetry run python examples/quickstart.py
```

### Run Tests

```bash
poetry run pytest
```

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🤝 Support

- **Documentation**: https://docs.starmoney.com
- **Issues**: https://github.com/Cloudymlhub/starmoney-bank-service/issues
- **Email**: dev@starmoney.com

## 🚀 Roadmap

- [ ] v0.2.0: Sync wrapper (requests-based)
- [ ] v0.3.0: Pagination support for list operations
- [ ] v0.4.0: Bulk payment operations
- [ ] v1.0.0: Stable API, production-ready

---

**Made with ❤️ by the StarMoney Team**
