from celery import shared_task

from .services import (
    delete_expired_idempotency_keys,
    pending_payout_ids,
    process_payout_attempt,
    retryable_processing_payout_ids,
)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_payout(self, payout_id: str) -> str:
    process_payout_attempt(payout_id)
    return payout_id


@shared_task
def scan_pending_payouts() -> int:
    payout_ids = pending_payout_ids()
    for payout_id in payout_ids:
        process_payout.delay(payout_id)
    return len(payout_ids)


@shared_task
def retry_stuck_payouts() -> int:
    payout_ids = retryable_processing_payout_ids()
    for payout_id in payout_ids:
        process_payout.delay(payout_id)
    return len(payout_ids)


@shared_task
def cleanup_expired_idempotency_keys() -> int:
    return delete_expired_idempotency_keys()

