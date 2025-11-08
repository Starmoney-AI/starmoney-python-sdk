"""
StarMoney SDK - Quickstart Example

Complete payment lifecycle demonstration matching the notebook workflow.
Shows: Create account → Link rail → Create beneficiary → Send payment → Check status
"""

import asyncio
from starmoney import StarmoneyClient


async def main():
    """Complete payment flow in < 20 lines."""

    # Initialize client
    async with StarmoneyClient(
        jwt_secret="your-jwt-secret-here",  # From .dev_secrets.json
        issuer="your-service-name",
        base_url="http://localhost:8000/starmoney/v1",
    ) as client:

        # 1. Create account
        print("Creating account...")
        account = await client.accounts.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone_number="+1234567890",
            document_type="PASSPORT",
            document_number="AB123456",
            address="123 Main St",
        )
        user_id = account["user_id"]
        print(f"✅ Account created: {user_id}")

        # 2. Link payment rail
        print("\nLinking payment rail...")
        await client.accounts.link_rail(user_id, rail_name="BDK")
        print("✅ Rail linked")

        # 3. Create beneficiary
        print("\nCreating beneficiary...")
        beneficiary = await client.beneficiaries.create(
            user_id=user_id,
            name="Jane Smith",
            iban="FR1420041010050500013M02606",
            currency="EUR",
            bank_name="Test Bank",
            address="456 Test Ave",
        )
        print(f"✅ Beneficiary created: {beneficiary['name']}")

        # 4. Send payment
        print("\nSending payment...")
        payment = await client.payments.send(
            user_id=user_id,
            amount=100.00,
            currency="EUR",
            beneficiary_iban=beneficiary["iban"],
            beneficiary_name=beneficiary["name"],
            description="Test payment via SDK",
        )

        client_txn_id = payment["client_transaction_id"]
        print("✅ Payment sent")
        print(f"   Transaction ID: {payment['transaction_id'][:8]}...")
        print(f"   Client TX ID: {client_txn_id}")

        # 5. Check payment status
        print("\nChecking payment status...")
        status = await client.payments.get_status(
            user_id=user_id, client_transaction_id=client_txn_id
        )
        print(f"✅ Status: {status['status']}")
        print(f"   Amount: {status['amount']} {status['currency']}")

        print("\n🎉 Payment flow completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
