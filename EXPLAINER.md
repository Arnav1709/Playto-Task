# EXPLAINER

## 1. The Ledger

Balance query:

```python
signed_amount = Case(
    When(entry_type__in=[LedgerEntry.Type.CREDIT, LedgerEntry.Type.RELEASE], then=F("amount_paise")),
    When(entry_type=LedgerEntry.Type.DEBIT, then=F("amount_paise") * Value(-1)),
    default=Value(0),
    output_field=BigIntegerField(),
)
result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    balance=Coalesce(Sum(signed_amount), Value(0), output_field=BigIntegerField())
)
```

Credits represent simulated customer payments. Debits represent payout holds, created immediately when a payout is requested. Releases represent failed payout reversals. The payout debit is not repeated on success because the money was already held.

## 2. The Lock

The overdraft prevention lives in `create_payout_idempotently`:

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    balances = balances_for_merchant(str(merchant.id))
    available_balance = balances["available_balance_paise"]

    if available_balance < amount_paise:
        return _complete_idempotency(..., 409)

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(
        merchant=merchant,
        payout=payout,
        entry_type=LedgerEntry.Type.DEBIT,
        amount_paise=amount_paise,
        description=f"Payout hold {payout.id}",
    )
```

This relies on PostgreSQL row-level locking through `SELECT ... FOR UPDATE`. Every payout request for the same merchant must acquire the merchant row lock before it can calculate balance and create the debit.

## 3. The Idempotency

`IdempotencyKey` has a unique constraint on `(merchant, key)`. The request body is canonicalized and stored as `request_hash`.

On each payout request the code locks the idempotency row with `select_for_update()`. If the first request is still in flight, the second request waits on that database row/unique constraint and then returns the stored response once the first transaction commits. If the same key is reused with a different body before expiry, the API returns `409 idempotency_key_reused`.

The stored response includes both `response_body` and `response_status_code`, so replay returns the exact same response body and status code.

## 4. The State Machine

Transition guard:

```python
ALLOWED_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
    Payout.Status.COMPLETED: set(),
    Payout.Status.FAILED: set(),
}

def transition_payout(payout: Payout, new_status: str, *, failure_reason: str = "") -> Payout:
    allowed = ALLOWED_TRANSITIONS.get(payout.status, set())
    if new_status not in allowed:
        raise InvalidPayoutTransition(f"Cannot transition payout from {payout.status} to {new_status}.")
```

`failed -> completed` is blocked because `Payout.Status.FAILED` maps to an empty set.

Failed payouts return funds in `fail_payout_and_release`, where the payout row is locked, the status changes to `failed`, and the release ledger entry is created inside the same transaction.

## 5. The AI Audit

Bad AI draft:

```python
entries = LedgerEntry.objects.filter(merchant=merchant)
balance = sum(entry.amount_paise for entry in entries)
if balance >= amount_paise:
    LedgerEntry.objects.create(...)
```

What was wrong:

- It summed in Python instead of the database.
- It did not lock the merchant row.
- Two simultaneous requests could both see the same balance and both create debits.

Replacement:

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    available_balance = balances_for_merchant(str(merchant.id))["available_balance_paise"]
    if available_balance < amount_paise:
        return _complete_idempotency(..., 409)
    LedgerEntry.objects.create(...)
```

That replacement keeps the balance check and debit creation inside one PostgreSQL transaction protected by a row lock.

