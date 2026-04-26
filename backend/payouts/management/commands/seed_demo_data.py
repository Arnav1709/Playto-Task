from django.core.management.base import BaseCommand
from django.db import transaction

from payouts.models import BankAccount, LedgerEntry, Merchant


class Command(BaseCommand):
    help = "Seed demo merchants, bank accounts, and customer-payment ledger credits."

    def handle(self, *args, **options):
        merchants = [
            {
                "name": "Acme Studio",
                "email": "acme@example.com",
                "credits": [
                    ("Invoice AC-1042 paid by Northwind LLC", 75_000),
                    ("Retainer payment from Blue Harbor Inc", 50_000),
                    ("Design sprint milestone from Orbit Labs", 25_000),
                ],
                "accounts": [
                    ("Riya Shah", "HDFC Bank", "XXXXXX4321", "HDFC0001234"),
                    ("Riya Shah", "ICICI Bank", "XXXXXX1188", "ICIC0002211"),
                ],
            },
            {
                "name": "Northstar Freelance",
                "email": "northstar@example.com",
                "credits": [
                    ("Landing page project paid by Atlas Digital", 100_000),
                    ("Monthly consulting payment from Finch AI", 90_000),
                    ("Brand audit payment from Maple Works", 60_000),
                ],
                "accounts": [
                    ("Kabir Mehta", "Axis Bank", "XXXXXX9090", "UTIB0004455"),
                ],
            },
            {
                "name": "Concurrency Test Merchant",
                "email": "concurrency@example.com",
                "credits": [
                    ("Concurrency test opening balance", 10_000),
                ],
                "accounts": [
                    ("Arnav Rao", "State Bank of India", "XXXXXX1000", "SBIN0007788"),
                ],
            },
        ]

        with transaction.atomic():
            for merchant_data in merchants:
                merchant, _ = Merchant.objects.update_or_create(
                    email=merchant_data["email"],
                    defaults={"name": merchant_data["name"]},
                )
                LedgerEntry.objects.filter(merchant=merchant, payout__isnull=True).delete()

                for holder, bank, masked, ifsc in merchant_data["accounts"]:
                    BankAccount.objects.update_or_create(
                        merchant=merchant,
                        masked_account_number=masked,
                        defaults={
                            "account_holder_name": holder,
                            "bank_name": bank,
                            "ifsc": ifsc,
                        },
                    )

                for description, amount_paise in merchant_data["credits"]:
                    LedgerEntry.objects.create(
                        merchant=merchant,
                        entry_type=LedgerEntry.Type.CREDIT,
                        amount_paise=amount_paise,
                        description=description,
                    )

        self.stdout.write(self.style.SUCCESS("Seeded Playto demo data."))
