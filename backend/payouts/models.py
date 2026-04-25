import uuid

from django.db import models
from django.db.models import Q


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Merchant(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    email = models.EmailField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BankAccount(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name="bank_accounts", on_delete=models.CASCADE)
    account_holder_name = models.CharField(max_length=160)
    bank_name = models.CharField(max_length=120)
    masked_account_number = models.CharField(max_length=32)
    ifsc = models.CharField(max_length=16)

    class Meta:
        ordering = ["bank_name", "masked_account_number"]

    def __str__(self) -> str:
        return f"{self.bank_name} {self.masked_account_number}"


class Payout(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name="payouts", on_delete=models.PROTECT)
    bank_account = models.ForeignKey(BankAccount, related_name="payouts", on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["status", "next_retry_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_paise__gt=0),
                name="payout_amount_paise_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.id} {self.status} {self.amount_paise}"


class LedgerEntry(models.Model):
    class Type(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"
        RELEASE = "release", "Release"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name="ledger_entries", on_delete=models.PROTECT)
    payout = models.ForeignKey(
        Payout,
        related_name="ledger_entries",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    entry_type = models.CharField(max_length=20, choices=Type.choices)
    amount_paise = models.BigIntegerField()
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "created_at"]),
            models.Index(fields=["entry_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_paise__gt=0),
                name="ledger_amount_paise_positive",
            ),
            models.UniqueConstraint(
                fields=["payout"],
                condition=Q(entry_type="debit", payout__isnull=False),
                name="one_debit_ledger_entry_per_payout",
            ),
            models.UniqueConstraint(
                fields=["payout"],
                condition=Q(entry_type="release", payout__isnull=False),
                name="one_release_ledger_entry_per_payout",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount_paise}"


class IdempotencyKey(TimestampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name="idempotency_keys", on_delete=models.CASCADE)
    key = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    response_body = models.JSONField(null=True, blank=True)
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["expires_at"])]
        constraints = [
            models.UniqueConstraint(fields=["merchant", "key"], name="unique_idempotency_key_per_merchant"),
        ]

    def __str__(self) -> str:
        return f"{self.merchant_id}:{self.key}"

