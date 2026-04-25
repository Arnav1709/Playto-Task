import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import BankAccount, LedgerEntry, Merchant, Payout
from .services import (
    InvalidPayoutTransition,
    balances_for_merchant,
    fail_payout_and_release,
    process_payout_attempt,
    transition_payout,
)


class PayoutEngineTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test Merchant", email="test@example.com")
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name="Test Merchant",
            bank_name="HDFC Bank",
            masked_account_number="XXXXXX1111",
            ifsc="HDFC0001111",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntry.Type.CREDIT,
            amount_paise=10_000,
            description="Initial customer payment",
        )

    def post_payout(self, amount_paise: int, idempotency_key: str):
        client = APIClient()
        return client.post(
            "/api/v1/payouts",
            {
                "amount_paise": amount_paise,
                "bank_account_id": str(self.bank_account.id),
            },
            format="json",
            HTTP_X_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )

    def test_concurrent_payouts_cannot_overdraw(self):
        barrier = Barrier(2)

        def submit(key: str):
            try:
                barrier.wait()
                return self.post_payout(6_000, key)
            finally:
                connections.close_all()

        with patch("payouts.tasks.process_payout.delay"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        submit,
                        [str(uuid.uuid4()), str(uuid.uuid4())],
                    )
                )

        status_codes = sorted(response.status_code for response in responses)
        self.assertEqual(status_codes, [201, 409])
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.filter(entry_type=LedgerEntry.Type.DEBIT).count(), 1)
        self.assertEqual(balances_for_merchant(str(self.merchant.id))["available_balance_paise"], 4_000)

    def test_idempotency_replays_exact_response(self):
        key = str(uuid.uuid4())
        with patch("payouts.tasks.process_payout.delay"):
            first = self.post_payout(6_000, key)
            second = self.post_payout(6_000, key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.filter(entry_type=LedgerEntry.Type.DEBIT).count(), 1)

    def test_idempotency_key_reuse_with_different_body_is_rejected(self):
        key = str(uuid.uuid4())
        with patch("payouts.tasks.process_payout.delay"):
            first = self.post_payout(3_000, key)
            second = self.post_payout(4_000, key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "idempotency_key_reused")
        self.assertEqual(Payout.objects.count(), 1)

    def test_failed_payout_releases_held_funds_atomically(self):
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank_account,
            amount_paise=6_000,
            status=Payout.Status.PENDING,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            payout=payout,
            entry_type=LedgerEntry.Type.DEBIT,
            amount_paise=6_000,
            description="Payout hold",
        )
        transition_payout(payout, Payout.Status.PROCESSING)

        fail_payout_and_release(str(payout.id), "Bank rejected the payout.")

        payout.refresh_from_db()
        balances = balances_for_merchant(str(self.merchant.id))
        self.assertEqual(payout.status, Payout.Status.FAILED)
        self.assertEqual(LedgerEntry.objects.filter(entry_type=LedgerEntry.Type.RELEASE).count(), 1)
        self.assertEqual(balances["available_balance_paise"], 10_000)
        self.assertEqual(balances["held_balance_paise"], 0)

    def test_failed_to_completed_transition_is_blocked(self):
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank_account,
            amount_paise=6_000,
            status=Payout.Status.FAILED,
        )

        with self.assertRaises(InvalidPayoutTransition):
            transition_payout(payout, Payout.Status.COMPLETED)

    def test_processing_payout_fails_after_max_hung_attempts_and_releases_once(self):
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account=self.bank_account,
            amount_paise=6_000,
            status=Payout.Status.PROCESSING,
            attempt_count=2,
            processing_started_at=timezone.now() - timedelta(seconds=45),
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            payout=payout,
            entry_type=LedgerEntry.Type.DEBIT,
            amount_paise=6_000,
            description="Payout hold",
        )

        process_payout_attempt(str(payout.id), outcome=0.95)
        process_payout_attempt(str(payout.id), outcome=0.95)

        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.FAILED)
        self.assertEqual(payout.attempt_count, 3)
        self.assertEqual(LedgerEntry.objects.filter(entry_type=LedgerEntry.Type.RELEASE).count(), 1)
        self.assertEqual(balances_for_merchant(str(self.merchant.id))["available_balance_paise"], 10_000)
