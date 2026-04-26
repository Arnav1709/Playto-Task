# Playto Payout Engine

Minimal payout engine for the Playto founding engineer challenge. It lets seeded merchants view ledger-derived balances, request INR payouts, and watch a real Celery worker move payouts through pending, processing, completed, and failed states.

## Stack

- Django 5.2 + Django REST Framework
- PostgreSQL
- Celery + Redis
- React + Vite + Tailwind
- Docker Compose for local development
- Railway-ready Dockerfile for web, worker, and beat services

## Local Setup

```bash
cp .env.example .env
docker compose up --build
```

In another shell:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_data
```

Open:

- API: `http://localhost:8000/api/v1/merchants`
- Frontend dev server: `http://localhost:5173`

## Useful Commands

```bash
# migrations
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate

# seed demo data
docker compose exec backend python manage.py seed_demo_data

# tests
docker compose exec backend python manage.py test payouts

# run services individually
docker compose up backend
docker compose up worker
docker compose up beat
docker compose up frontend
```

## API

All merchant-scoped endpoints require `X-Merchant-ID`.

```http
GET /api/v1/merchants
GET /api/v1/merchant/dashboard
GET /api/v1/payouts
GET /api/v1/payouts/<payout_id>
POST /api/v1/payouts
Idempotency-Key: <uuid>
```

Create payout body:

```json
{
  "amount_paise": 6000,
  "bank_account_id": "<uuid>"
}
```

## Demo Data

`seed_demo_data` creates:

- `Acme Studio`
- `Northstar Freelance`
- `Concurrency Test Merchant`

The concurrency merchant starts with exactly `10000` paise so two simultaneous `6000` paise payout requests should produce one success and one insufficient-funds response.

## Railway Deployment

Create one Railway project with PostgreSQL and Redis services, then create three services from this repo using the root `Dockerfile`.

Use the same environment variables for all app services:

```bash
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<your-domain>.up.railway.app,.railway.app
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
DATABASE_SSL_REQUIRE=True
```

Service commands:

```bash
# web
python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT

# worker
celery -A config worker --loglevel=info

# beat
celery -A config beat --loglevel=info
```

After deploy:

```bash
python manage.py seed_demo_data
```

Deployment URL: `TODO`

## Notes

- Money is always stored as paise in `BigIntegerField`.
- Balance is derived from ledger rows with database aggregation.
- Dashboard labels use plain language:
  - `Ready to withdraw` = available balance.
  - `Being paid out` = funds locked by pending/processing payouts.
  - `Still with Playto` = ready to withdraw + being paid out.
- Payout creation uses `transaction.atomic()` and `select_for_update()` to prevent double spend.
- Idempotency keys are unique per merchant and store the exact response body and status code.
- Failed payouts release funds in the same transaction as the failed state transition.
