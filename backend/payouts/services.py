import hashlib
import json
import random
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import BigIntegerField, Case, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout

IDEMPOTENCY_TTL = timedelta(hours=24)
MAX_PAYOUT_ATTEMPTS = 3
BASE_RETRY_SECONDS = 30
PROCESSING_STALE_AFTER = timedelta(seconds=30)

ALLOWED_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
    Payout.Status.COMPLETED: set(),
    Payout.Status.FAILED: set(),
}


class InvalidPayoutTransition(ValueError):
    pass


def canonical_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ledger_balance_for_merchant(merchant_id: str) -> int:
    signed_amount = Case(
        When(entry_type__in=[LedgerEntry.Type.CREDIT, LedgerEntry.Type.RELEASE], then=F("amount_paise")),
        When(entry_type=LedgerEntry.Type.DEBIT, then=F("amount_paise") * Value(-1)),
        default=Value(0),
        output_field=BigIntegerField(),
    )
    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        balance=Coalesce(Sum(signed_amount), Value(0), output_field=BigIntegerField())
    )
    return int(result["balance"] or 0)


def held_balance_for_merchant(merchant_id: str) -> int:
    result = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
    ).aggregate(
        held=Coalesce(Sum("amount_paise"), Value(0), output_field=BigIntegerField())
    )
    return int(result["held"] or 0)


def balances_for_merchant(merchant_id: str) -> dict[str, int]:
    available = ledger_balance_for_merchant(merchant_id)
    held = held_balance_for_merchant(merchant_id)
    return {
        "available_balance_paise": available,
        "held_balance_paise": held,
        "total_balance_paise": available + held,
    }


def payout_response_body(payout: Payout) -> dict[str, Any]:
    return {
        "id": str(payout.id),
        "merchant_id": str(payout.merchant_id),
        "amount_paise": payout.amount_paise,
        "bank_account_id": str(payout.bank_account_id),
        "status": payout.status,
        "attempt_count": payout.attempt_count,
        "created_at": payout.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": payout.updated_at.isoformat().replace("+00:00", "Z"),
    }


def _error_body(code: str, message: str) -> dict[str, str]:
    return {"error": code, "message": message}


def _complete_idempotency(
    idem: IdempotencyKey,
    body: dict[str, Any],
    status_code: int,
) -> tuple[dict[str, Any], int]:
    idem.response_body = body
    idem.response_status_code = status_code
    idem.status = IdempotencyKey.Status.COMPLETED
    idem.save(update_fields=["response_body", "response_status_code", "status", "updated_at"])
    return body, status_code


def _get_or_create_locked_idempotency(
    merchant_id: str,
    key: str,
    request_hash: str,
    now,
) -> tuple[IdempotencyKey, bool]:
    try:
        return (
            IdempotencyKey.objects.select_for_update().get(merchant_id=merchant_id, key=key),
            False,
        )
    except IdempotencyKey.DoesNotExist:
        try:
            with transaction.atomic():
                return (
                    IdempotencyKey.objects.create(
                        merchant_id=merchant_id,
                        key=key,
                        request_hash=request_hash,
                        status=IdempotencyKey.Status.IN_PROGRESS,
                        expires_at=now + IDEMPOTENCY_TTL,
                    ),
                    True,
                )
        except IntegrityError:
            return (
                IdempotencyKey.objects.select_for_update().get(merchant_id=merchant_id, key=key),
                False,
            )


def create_payout_idempotently(
    *,
    merchant_id: str,
    amount_paise: int,
    bank_account_id: str,
    idempotency_key: str,
) -> tuple[dict[str, Any], int]:
    now = timezone.now()
    request_payload = {
        "amount_paise": amount_paise,
        "bank_account_id": str(bank_account_id),
    }
    request_hash = canonical_request_hash(request_payload)

    with transaction.atomic():
        idem, is_new = _get_or_create_locked_idempotency(
            merchant_id=merchant_id,
            key=idempotency_key,
            request_hash=request_hash,
            now=now,
        )

        if not is_new and idem.expires_at <= now:
            idem.request_hash = request_hash
            idem.response_body = None
            idem.response_status_code = None
            idem.status = IdempotencyKey.Status.IN_PROGRESS
            idem.expires_at = now + IDEMPOTENCY_TTL
            idem.save(
                update_fields=[
                    "request_hash",
                    "response_body",
                    "response_status_code",
                    "status",
                    "expires_at",
                    "updated_at",
                ]
            )
            is_new = True

        if not is_new:
            if idem.request_hash != request_hash:
                return (
                    _error_body(
                        "idempotency_key_reused",
                        "This idempotency key was already used with a different request body.",
                    ),
                    409,
                )
            if idem.status == IdempotencyKey.Status.COMPLETED and idem.response_body is not None:
                return idem.response_body, int(idem.response_status_code)
            return (
                _error_body(
                    "idempotency_key_in_progress",
                    "A request with this idempotency key is still being processed.",
                ),
                409,
            )

        try:
            bank_account = BankAccount.objects.get(id=bank_account_id, merchant_id=merchant_id)
        except (BankAccount.DoesNotExist, ValueError):
            return _complete_idempotency(
                idem,
                _error_body("invalid_bank_account", "Bank account does not belong to this merchant."),
                400,
            )

        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        balances = balances_for_merchant(str(merchant.id))
        available_balance = balances["available_balance_paise"]

        if available_balance < amount_paise:
            return _complete_idempotency(
                idem,
                _error_body(
                    "insufficient_funds",
                    f"Available balance is {available_balance} paise, requested {amount_paise} paise.",
                ),
                409,
            )

        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.Status.PENDING,
        )
        LedgerEntry.objects.create(
            merchant=merchant,
            payout=payout,
            entry_type=LedgerEntry.Type.DEBIT,
            amount_paise=amount_paise,
            description=f"Payout hold {payout.id}",
        )

        body, status_code = _complete_idempotency(idem, payout_response_body(payout), 201)

        def enqueue_payout() -> None:
            from .tasks import process_payout

            process_payout.delay(str(payout.id))

        transaction.on_commit(enqueue_payout)
        return body, status_code


def transition_payout(payout: Payout, new_status: str, *, failure_reason: str = "") -> Payout:
    allowed = ALLOWED_TRANSITIONS.get(payout.status, set())
    if new_status not in allowed:
        raise InvalidPayoutTransition(f"Cannot transition payout from {payout.status} to {new_status}.")

    now = timezone.now()
    payout.status = new_status
    update_fields = ["status", "updated_at"]

    if new_status == Payout.Status.PROCESSING:
        payout.processing_started_at = now
        update_fields.append("processing_started_at")
    elif new_status == Payout.Status.COMPLETED:
        payout.completed_at = now
        payout.next_retry_at = None
        update_fields.extend(["completed_at", "next_retry_at"])
    elif new_status == Payout.Status.FAILED:
        payout.failed_at = now
        payout.failure_reason = failure_reason
        payout.next_retry_at = None
        update_fields.extend(["failed_at", "failure_reason", "next_retry_at"])

    payout.save(update_fields=update_fields)
    return payout


def _release_failed_funds_locked(payout: Payout) -> None:
    LedgerEntry.objects.get_or_create(
        merchant=payout.merchant,
        payout=payout,
        entry_type=LedgerEntry.Type.RELEASE,
        defaults={
            "amount_paise": payout.amount_paise,
            "description": f"Release failed payout {payout.id}",
        },
    )


def fail_payout_and_release(payout_id: str, reason: str) -> Payout:
    with transaction.atomic():
        payout = (
            Payout.objects.select_for_update()
            .select_related("merchant")
            .get(id=payout_id)
        )
        if payout.status == Payout.Status.FAILED:
            _release_failed_funds_locked(payout)
            return payout
        transition_payout(payout, Payout.Status.FAILED, failure_reason=reason)
        _release_failed_funds_locked(payout)
        return payout


def complete_payout(payout_id: str) -> Payout | None:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        if payout.status != Payout.Status.PROCESSING:
            return None
        return transition_payout(payout, Payout.Status.COMPLETED)


def retry_delay_for_attempt(attempt_count: int) -> timedelta:
    delay_seconds = BASE_RETRY_SECONDS * (2 ** max(attempt_count - 1, 0))
    return timedelta(seconds=delay_seconds)


def _processing_due(payout: Payout, now) -> bool:
    if payout.next_retry_at and payout.next_retry_at <= now:
        return True
    if payout.processing_started_at and payout.processing_started_at <= now - PROCESSING_STALE_AFTER:
        return True
    return False


def mark_payout_hung_or_failed(payout_id: str) -> Payout | None:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().select_related("merchant").get(id=payout_id)
        if payout.status != Payout.Status.PROCESSING:
            return None
        if payout.attempt_count >= MAX_PAYOUT_ATTEMPTS:
            transition_payout(
                payout,
                Payout.Status.FAILED,
                failure_reason="Bank settlement timed out after max retries.",
            )
            _release_failed_funds_locked(payout)
            return payout

        payout.next_retry_at = timezone.now() + retry_delay_for_attempt(payout.attempt_count)
        payout.failure_reason = "Bank settlement timed out; retry scheduled."
        payout.save(update_fields=["next_retry_at", "failure_reason", "updated_at"])
        return payout


def process_payout_attempt(payout_id: str, *, outcome: float | None = None) -> Payout | None:
    now = timezone.now()
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        if payout.status == Payout.Status.PENDING:
            transition_payout(payout, Payout.Status.PROCESSING)
            payout.refresh_from_db()
        elif payout.status == Payout.Status.PROCESSING and not _processing_due(payout, now):
            return None
        elif payout.status != Payout.Status.PROCESSING:
            return None

        if payout.attempt_count >= MAX_PAYOUT_ATTEMPTS:
            transition_payout(
                payout,
                Payout.Status.FAILED,
                failure_reason="Payout exhausted retries before another bank attempt.",
            )
            _release_failed_funds_locked(payout)
            return payout

        payout.attempt_count += 1
        payout.last_attempted_at = now
        payout.processing_started_at = now
        payout.next_retry_at = None
        payout.save(
            update_fields=[
                "attempt_count",
                "last_attempted_at",
                "processing_started_at",
                "next_retry_at",
                "updated_at",
            ]
        )

    bank_outcome = random.random() if outcome is None else outcome
    if bank_outcome < 0.7:
        return complete_payout(payout_id)
    if bank_outcome < 0.9:
        return fail_payout_and_release(payout_id, "Bank rejected the payout.")
    return mark_payout_hung_or_failed(payout_id)


def pending_payout_ids(batch_size: int = 25) -> list[str]:
    with transaction.atomic():
        payout_ids = list(
            Payout.objects.select_for_update(skip_locked=True)
            .filter(status=Payout.Status.PENDING)
            .order_by("created_at")
            .values_list("id", flat=True)[:batch_size]
        )
    return [str(payout_id) for payout_id in payout_ids]


def retryable_processing_payout_ids(batch_size: int = 25) -> list[str]:
    now = timezone.now()
    stale_before = now - PROCESSING_STALE_AFTER
    with transaction.atomic():
        payout_ids = list(
            Payout.objects.select_for_update(skip_locked=True)
            .filter(status=Payout.Status.PROCESSING)
            .filter(Q(next_retry_at__lte=now) | Q(processing_started_at__lte=stale_before))
            .order_by("next_retry_at", "processing_started_at")
            .values_list("id", flat=True)[:batch_size]
        )
    return [str(payout_id) for payout_id in payout_ids]


def delete_expired_idempotency_keys() -> int:
    deleted_count, _ = IdempotencyKey.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted_count

