# Playto Payout Engine PRD

## 1. Purpose

Build a minimal payout engine for Playto Pay where Indian merchants can:

- View available and held balance in paise.
- Request INR payouts to a saved bank account.
- Track payout status in near real time.
- Trust that money cannot be overdrawn, duplicated, or lost during payout failures/retries.

This is a technical challenge, so the priority is correctness of money movement over UI polish.

## 2. Success Criteria

The submission is successful when:

- The backend is a Django + DRF service using PostgreSQL.
- The frontend is a React + Tailwind dashboard.
- Background payout processing is handled by a real worker system such as Celery, Huey, or Django-Q.
- Merchant balances are stored and calculated in paise using integer fields only.
- Concurrent payout requests cannot overdraw a merchant balance.
- Idempotent payout requests return the exact same response for repeated keys.
- Payout state transitions are enforced by code.
- Failed payouts atomically return held funds.
- Stuck processing payouts are retried with exponential backoff and fail after 3 attempts.
- At least 2 meaningful tests exist: one for concurrency and one for idempotency.
- README, seed script, deployment, and EXPLAINER.md are complete.

## 3. Recommended Stack

- Backend: Django, Django REST Framework
- Database: PostgreSQL
- Background jobs: Celery + Redis
- Frontend: React, Vite, Tailwind
- Deployment: Render, Railway, Fly.io, Koyeb, or similar
- Optional local infra: docker-compose for Postgres + Redis + backend + worker + frontend

## 4. Users

### Merchant

A merchant is an Indian agency or freelancer who receives international payments through Playto and withdraws INR to a bank account.

Merchant capabilities:

- See available balance.
- See held balance.
- See recent ledger entries.
- Request a payout.
- See payout history and statuses.

### System Worker

The payout processor is a background worker that:

- Picks pending payouts.
- Moves them to processing.
- Simulates bank settlement.
- Marks payouts completed or failed.
- Retries stuck processing payouts.
- Returns funds on failure.

## 5. Core Product Scope

### In Scope

- Seeded merchants.
- Seeded bank accounts.
- Seeded customer payment credits.
- Ledger-based balances.
- Payout request API with idempotency.
- Payout lifecycle processing.
- Retry handling for stuck payouts.
- Merchant dashboard.
- Basic authentication or merchant selection suitable for demo.
- Tests for concurrency and idempotency.
- Deployment with test data.
- README.md and EXPLAINER.md.

### Out of Scope

- Real customer payment collection.
- Real bank integrations.
- Multi-currency FX conversion.
- Full production auth/KYC.
- Admin panel polish.
- Pixel-perfect UI.
- Webhooks unless chosen as optional bonus.

## 6. Money Model

All money is stored as paise using `BigIntegerField`.

Do not use:

- `FloatField`
- Python float arithmetic
- Client-side balance calculation

Recommended model:

### Merchant

Fields:

- `id`
- `name`
- `email`
- `created_at`

### BankAccount

Fields:

- `id`
- `merchant`
- `account_holder_name`
- `bank_name`
- `masked_account_number`
- `ifsc`
- `created_at`

### LedgerEntry

Fields:

- `id`
- `merchant`
- `entry_type`: `credit`, `debit`, `release`
- `amount_paise`: positive integer
- `payout`: nullable FK
- `description`
- `created_at`

Rules:

- Customer payments create `credit` entries.
- Payout requests create `debit` entries immediately to hold funds.
- Failed payouts create `release` entries to return funds.
- Completed payouts do not create another debit because the money was already held at request time.

Balance formulas:

- Available balance = `SUM(credit + release - debit)`
- Held balance = `SUM(debit for payouts pending/processing) - SUM(release for failed payouts)`
- Total merchant balance = available balance + held balance

Important: available balance should be calculated by database aggregation, not by fetching rows and summing in Python.

## 7. Payout State Machine

Payout statuses:

- `pending`
- `processing`
- `completed`
- `failed`

Legal transitions:

- `pending -> processing`
- `processing -> completed`
- `processing -> failed`

Illegal transitions:

- `completed -> pending`
- `completed -> processing`
- `completed -> failed`
- `failed -> pending`
- `failed -> processing`
- `failed -> completed`
- Any backwards transition

The transition function should enforce this centrally, for example:

```python
ALLOWED_TRANSITIONS = {
    "pending": {"processing"},
    "processing": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}
```

When a payout fails, the status update and ledger release entry must happen in the same database transaction.

## 8. Idempotency Requirements

Endpoint:

```http
POST /api/v1/payouts
Idempotency-Key: merchant-supplied-uuid
Content-Type: application/json
```

Body:

```json
{
  "amount_paise": 6000,
  "bank_account_id": "..."
}
```

Rules:

- Idempotency key is required.
- Key is scoped per merchant.
- Same merchant + same key must return the exact same response body and status code.
- Same key for different merchants is allowed.
- Keys expire after 24 hours.
- If request A is still in flight and request B arrives with the same key, request B must not create a duplicate payout.

Recommended model:

### IdempotencyKey

Fields:

- `id`
- `merchant`
- `key`
- `request_hash`
- `response_body`
- `response_status_code`
- `status`: `in_progress`, `completed`, `failed`
- `expires_at`
- `created_at`
- `updated_at`

Constraints:

- Unique constraint on `(merchant, key)`.

Behavior:

- On first request, create an `in_progress` idempotency row inside a transaction.
- On duplicate request:
  - If completed, return stored response exactly.
  - If in progress, lock the idempotency row and wait until the first request commits, or return a clean conflict/retry response depending on implementation.
- If same key is reused with a different request body before expiry, reject it.

## 9. Concurrency Requirements

Scenario:

- Merchant has 100 rupees available balance.
- Two simultaneous payout requests of 60 rupees arrive.
- Exactly one payout should be created.
- The other request should return a clean insufficient funds error.

Recommended locking approach:

- Wrap payout creation in `transaction.atomic()`.
- Lock the merchant row using `select_for_update()`.
- Calculate available balance using DB aggregation inside the transaction.
- If balance is insufficient, reject.
- If sufficient, create payout and ledger debit entry in the same transaction.

The lock must rely on PostgreSQL row-level locking, not Python locks.

## 10. API Requirements

### Get Dashboard Summary

```http
GET /api/v1/merchant/dashboard
```

Returns:

```json
{
  "merchant": {
    "id": "...",
    "name": "Acme Studio"
  },
  "available_balance_paise": 150000,
  "held_balance_paise": 60000,
  "recent_ledger_entries": [],
  "recent_payouts": []
}
```

### Create Payout

```http
POST /api/v1/payouts
Idempotency-Key: uuid
```

Possible responses:

- `201 Created`: payout created
- `200 OK` or same original status: duplicate idempotent response
- `400 Bad Request`: invalid amount or bank account
- `402 Payment Required` or `409 Conflict`: insufficient funds
- `409 Conflict`: idempotency key in progress or body mismatch

### List Payouts

```http
GET /api/v1/payouts
```

Returns payout history for the merchant.

### Optional Polling Endpoint

```http
GET /api/v1/payouts/:id
```

Returns current status for one payout.

## 11. Background Processing

Worker responsibilities:

1. Pick `pending` payouts.
2. Lock each payout row.
3. Transition `pending -> processing`.
4. Simulate bank result:
   - 70 percent completed
   - 20 percent failed
   - 10 percent stuck in processing
5. On success, transition `processing -> completed`.
6. On failure, transition `processing -> failed` and create release ledger entry atomically.
7. Separately scan for `processing` payouts older than 30 seconds.
8. Retry stuck payouts with exponential backoff.
9. After 3 attempts, mark failed and return funds.

Recommended fields on Payout:

- `id`
- `merchant`
- `bank_account`
- `amount_paise`
- `status`
- `attempt_count`
- `next_retry_at`
- `processing_started_at`
- `completed_at`
- `failed_at`
- `failure_reason`
- `created_at`
- `updated_at`

## 12. Frontend Requirements

Build a React + Tailwind merchant dashboard.

Screen sections:

- Balance summary:
  - Available balance
  - Held balance
  - Total balance
- Payout form:
  - Amount input
  - Bank account selector
  - Submit button
  - Loading, success, and error states
- Recent ledger entries:
  - Type
  - Amount
  - Description
  - Timestamp
- Payout history:
  - Amount
  - Bank account
  - Status
  - Attempts
  - Created time
  - Updated time

Live updates:

- Poll dashboard/payout endpoints every few seconds, or use WebSocket/SSE if time permits.
- Polling is acceptable for this challenge.

## 13. Seed Data

Seed script should create:

- 2 to 3 merchants.
- 1 to 2 bank accounts per merchant.
- Credit history for each merchant.
- At least one merchant with exactly enough balance to manually test concurrency.

Suggested sample:

- Merchant A: 100000 paise available
- Merchant B: 250000 paise available
- Merchant C: 75000 paise available

## 14. Tests

Minimum required tests:

### Concurrency Test

Setup:

- Merchant has 10000 paise available.
- Fire two simultaneous payout requests for 6000 paise.

Expected:

- One request succeeds.
- One request fails with insufficient funds.
- Only one payout exists.
- Ledger balance remains correct.

### Idempotency Test

Setup:

- Send payout request with an idempotency key.
- Send the exact same request again with the same key.

Expected:

- Second response equals first response.
- Only one payout exists.
- Only one debit ledger entry exists.

Additional useful tests:

- Failed payout returns funds.
- Failed-to-completed transition is rejected.
- Reusing an idempotency key with different body is rejected.
- Processing payout older than 30 seconds is retried.
- Payout fails after max attempts and releases funds.

## 15. README Requirements

README.md should include:

- Project overview.
- Tech stack.
- Local setup instructions.
- Environment variables.
- How to run migrations.
- How to seed data.
- How to run API server.
- How to run worker.
- How to run frontend.
- How to run tests.
- Demo credentials or merchant IDs.
- Deployment URL.

## 16. EXPLAINER.md Requirements

Answer these exactly and specifically:

1. The Ledger
   - Paste the balance calculation query.
   - Explain why credits/debits/releases were modeled this way.

2. The Lock
   - Paste the exact code using `transaction.atomic()` and `select_for_update()`.
   - Explain that it relies on PostgreSQL row-level locks.

3. The Idempotency
   - Explain how `(merchant, key)` uniquely identifies a request.
   - Explain what happens when a second request arrives while the first is in flight.

4. The State Machine
   - Paste the transition guard.
   - Show where `failed -> completed` is blocked.

5. The AI Audit
   - Include one honest mistake AI made.
   - Example: AI initially calculated balance in Python or checked balance before locking.
   - Paste the wrong version, what was caught, and the replacement.

## 17. Implementation Milestones

### Milestone 1: Project Setup

- Create Django backend.
- Create React frontend.
- Configure PostgreSQL.
- Configure Redis + Celery.
- Add docker-compose if time allows.

### Milestone 2: Core Backend Models

- Merchant
- BankAccount
- LedgerEntry
- Payout
- IdempotencyKey
- Migrations
- Seed command

### Milestone 3: Balance and Ledger Logic

- Implement DB aggregation balance service.
- Add available balance and held balance calculation.
- Add tests for seeded balances.

### Milestone 4: Payout Request API

- Implement POST `/api/v1/payouts`.
- Add idempotency handling.
- Add merchant locking.
- Create payout and debit ledger entry atomically.

### Milestone 5: Payout Processor

- Add Celery task for pending payouts.
- Add status transition function.
- Add settlement simulation.
- Add failure release logic.
- Add stuck processing retry task.

### Milestone 6: Tests

- Write concurrency test.
- Write idempotency test.
- Add state transition and failure release tests if time allows.

### Milestone 7: Frontend

- Dashboard layout.
- Balance cards.
- Payout form.
- Ledger table.
- Payout history table.
- Polling for live status updates.

### Milestone 8: Docs and Deployment

- README.md.
- EXPLAINER.md.
- Deploy backend, worker, DB, Redis, and frontend.
- Seed hosted environment.
- Verify demo flow.

## 18. Suggested Time Plan

For 10 to 15 focused hours:

- 1 hour: project setup and infra
- 2 hours: models, migrations, seed data
- 2 hours: ledger and balance logic
- 2 hours: payout API, idempotency, locking
- 2 hours: worker, state machine, retries
- 1.5 hours: tests
- 1.5 hours: frontend
- 1 hour: README, EXPLAINER, deployment cleanup

## 19. Main Engineering Risks

- Calculating balances in Python instead of database aggregation.
- Checking balance before acquiring a row lock.
- Creating idempotency records outside the payout transaction.
- Returning a second response before the first idempotent request has committed.
- Creating duplicate debit ledger entries for repeated requests.
- Marking failed payouts without releasing funds in the same transaction.
- Allowing illegal state transitions through direct model saves.
- Letting stuck processing payouts stay stuck forever.

## 20. Definition of Done

The task is done when:

- Local backend, worker, frontend, Postgres, and Redis run successfully.
- Seed script creates demo merchants and ledger credits.
- Dashboard shows correct balances.
- Payout form creates pending payouts.
- Worker moves payouts through statuses.
- Failed payouts return funds.
- Retried payouts respect max attempts.
- Concurrency test passes.
- Idempotency test passes.
- README.md explains setup clearly.
- EXPLAINER.md answers all required questions with code snippets.
- Hosted deployment is live and seeded.

