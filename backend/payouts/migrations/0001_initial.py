# Generated for the Playto founding engineer challenge.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Merchant",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("email", models.EmailField(max_length=254, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="IdempotencyKey",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=64)),
                ("request_hash", models.CharField(max_length=64)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("response_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("in_progress", "In progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="in_progress",
                        max_length=20,
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="idempotency_keys",
                        to="payouts.merchant",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account_holder_name", models.CharField(max_length=160)),
                ("bank_name", models.CharField(max_length=120)),
                ("masked_account_number", models.CharField(max_length=32)),
                ("ifsc", models.CharField(max_length=16)),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bank_accounts",
                        to="payouts.merchant",
                    ),
                ),
            ],
            options={"ordering": ["bank_name", "masked_account_number"]},
        ),
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount_paise", models.BigIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_attempted_at", models.DateTimeField(blank=True, null=True)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.CharField(blank=True, max_length=255)),
                (
                    "bank_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payouts",
                        to="payouts.bankaccount",
                    ),
                ),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payouts",
                        to="payouts.merchant",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "entry_type",
                    models.CharField(
                        choices=[("credit", "Credit"), ("debit", "Debit"), ("release", "Release")],
                        max_length=20,
                    ),
                ),
                ("amount_paise", models.BigIntegerField()),
                ("description", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_entries",
                        to="payouts.merchant",
                    ),
                ),
                (
                    "payout",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_entries",
                        to="payouts.payout",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="idempotencykey",
            index=models.Index(fields=["expires_at"], name="payouts_ide_expires_f51cdf_idx"),
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["status", "created_at"], name="payouts_pay_status_dd1f82_idx"),
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(fields=["status", "next_retry_at"], name="payouts_pay_status_0e8e83_idx"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["merchant", "created_at"], name="payouts_led_merchan_37f31e_idx"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["entry_type"], name="payouts_led_entry_t_87b7c1_idx"),
        ),
        migrations.AddConstraint(
            model_name="idempotencykey",
            constraint=models.UniqueConstraint(
                fields=("merchant", "key"),
                name="unique_idempotency_key_per_merchant",
            ),
        ),
        migrations.AddConstraint(
            model_name="payout",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paise__gt", 0)),
                name="payout_amount_paise_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paise__gt", 0)),
                name="ledger_amount_paise_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("entry_type", "debit"), ("payout__isnull", False)),
                fields=("payout",),
                name="one_debit_ledger_entry_per_payout",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("entry_type", "release"), ("payout__isnull", False)),
                fields=("payout",),
                name="one_release_ledger_entry_per_payout",
            ),
        ),
    ]
