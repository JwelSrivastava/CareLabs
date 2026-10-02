# CareLabs

Diagnostic test booking and simulated payment service.

## 1. Project overview

CareLabs lets a signed-in patient book a diagnostic test at a centre, pay for that booking through a simulated provider, and receive a later provider result on a webhook. Staff with the admin role manage centres, tests, and the price each centre charges.

Public identifiers are UUIDs. Configuration comes from environment variables. Passwords are stored only as Argon2id hashes.

## 2. Architecture

HTTP routes validate input and map service errors to status codes. Services hold the booking and payment rules. SQLAlchemy models own the schema, and Alembic migrates it. One database session is created per request.

```text
app/
  main.py                 FastAPI app and /health
  api/routes/             auth, centres, tests, bookings, payments
  api/deps.py             current user and admin checks
  core/                   settings, database session, password and JWT helpers
  models/                 users, centres, tests, offerings, bookings, payments
  schemas/                request and response models
  services/               business rules and transactions
  repositories/           user lookup by email
  scripts/create_admin.py admin account command
alembic/                  migrations
tests/                    pytest suite
```

Routes do not calculate prices or change booking state on their own. Payment and booking updates that belong together are committed in one transaction.

## 3. Technology stack

- Python 3.12+ (the Docker image uses 3.12)
- FastAPI and Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.x and Alembic
- Pydantic v2
- PyJWT (HS256)
- pwdlib with Argon2id
- psycopg
- pytest and httpx
- Docker Compose

## 4. Database schema explanation

| Table | Purpose | Important constraints |
| --- | --- | --- |
| `users` | Accounts | Unique email, role `USER` or `ADMIN` |
| `diagnostic_centres` | Labs | Unique pair of name and location |
| `diagnostic_tests` | Test catalogue | Unique name. No price on this table |
| `centre_tests` | A test offered by one centre | Unique `(centre_id, test_id)`, price greater than 0. Deleting a centre or test deletes its offerings |
| `bookings` | An appointment | Amount greater than 0. One active booking per user, centre, test, and appointment. Active means `PENDING` or `CONFIRMED`. Foreign keys restrict deletion of the user, centre, and test |
| `payments` | One charge for a booking | Unique `booking_id`, unique `payment_reference`, unique `provider_transaction_id` when present. Amount greater than 0 |

Booking statuses are `PENDING`, `CONFIRMED`, `FAILED`, and `CANCELLED`. Payment statuses are `PENDING`, `SUCCESS`, and `FAILED`. A new simulated charge is written as `SUCCESS` or `FAILED` immediately, so a live payment row does not stay `PENDING`.

Naive appointment times are stored as UTC. PostgreSQL may return that instant with the session's local offset. `2027-10-15T10:00:00` and `2027-10-15T15:30:00+05:30` are the same moment.

## 5. Setup instructions

From a clean clone:

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. Replace `POSTGRES_PASSWORD`, `DATABASE_URL`, and `JWT_SECRET`. Use the same user, password, and database name in `DATABASE_URL` and the `POSTGRES_*` variables. Then start the stack:

```bash
docker compose up --build
```

When the API is healthy:

```bash
curl http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:8000/docs`.

Create the first admin after the database is up. Put real values in the environment, not the placeholders from `.env.example`:

```powershell
$env:ADMIN_NAME = "Ada Admin"
$env:ADMIN_EMAIL = "ada@example.com"
$env:ADMIN_PASSWORD = "replace-with-a-long-password"
python -m app.scripts.create_admin
```

The command prints `created`, `promoted`, or `exists`, plus the email. It does not print the password. Signup cannot choose a role, so this command is the way to get an admin. An existing user with the same email is promoted and keeps the current password. Run it again and it leaves an existing admin unchanged.

If the API is running in Compose and those three variables are set in `.env`, the same command works inside the container:

```bash
docker compose exec api python -m app.scripts.create_admin
```

To run Uvicorn on the host instead of in Compose, start only Postgres (`docker compose up -d postgres`), apply migrations, then start the app:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The host process reads `DATABASE_URL` from `.env`, which points at `localhost`.

## 6. Environment variables

| Variable | Used by | Meaning |
| --- | --- | --- |
| `APP_NAME` | API | Service name. Default `CareLabs` |
| `APP_ENV` | API | Environment label. Default `local` |
| `POSTGRES_USER` | Postgres container | Database user |
| `POSTGRES_PASSWORD` | Postgres container | Database password |
| `POSTGRES_DB` | Postgres container | Database name |
| `POSTGRES_PORT` | Compose | Host port for Postgres. Default `5432` |
| `DATABASE_URL` | Host API, Alembic, pytest | SQLAlchemy URL. The API container does not use the host URL |
| `JWT_SECRET` | API | HMAC secret for access tokens |
| `JWT_ALGORITHM` | API | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | API | Access token lifetime. Default `60` |
| `API_PORT` | Compose | Host port for the API. Default `8000` |
| `ADMIN_NAME` | Admin command | Display name for the admin account |
| `ADMIN_EMAIL` | Admin command | Admin email |
| `ADMIN_PASSWORD` | Admin command | Admin password, 8 to 128 characters |

`.env` is gitignored. Do not commit it.

## 7. Docker instructions

`docker-compose.yml` starts two services:

- `postgres` is `postgres:16-alpine`. Credentials come from `.env`. Data is stored in the `carelabs_postgres_data` volume. The service is healthy when `pg_isready` succeeds.
- `api` is built from the Dockerfile. It waits for a healthy database, runs `alembic upgrade head`, then serves Uvicorn on port 8000. Its `DATABASE_URL` uses the hostname `postgres`, not `localhost`.

```bash
docker compose up --build
docker compose ps
docker compose logs api
docker compose down
```

`docker compose down` keeps the database volume. `docker compose down -v` deletes it.

The image runs as a non-root user. It does not copy `.env` or the test suite. Secrets are passed in at runtime.

## 8. Migration instructions

Alembic reads `DATABASE_URL` from the environment. The placeholder URL in `alembic.ini` is not used.

On the host, with Postgres already running:

```bash
alembic upgrade head
alembic downgrade -1
alembic history
```

The API container runs `alembic upgrade head` before it starts listening. Current revisions create users, centres, tests, centre offerings, bookings, and payments.

## 9. API documentation

Interactive docs are at `/docs` and `/redoc`. All versioned routes are under `/api/v1`.

| Method | Path | Who | Success |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | 200 |
| `POST` | `/api/v1/auth/signup` | Public | 201 |
| `POST` | `/api/v1/auth/login` | Public | 200 |
| `GET` | `/api/v1/auth/me` | Signed in | 200 |
| `GET` | `/api/v1/centres` | Signed in | 200 |
| `GET` | `/api/v1/centres/{centre_id}` | Signed in | 200 |
| `POST` | `/api/v1/centres` | Admin | 201 |
| `PUT` | `/api/v1/centres/{centre_id}` | Admin | 200 |
| `DELETE` | `/api/v1/centres/{centre_id}` | Admin | 204 |
| `GET` | `/api/v1/tests` | Signed in | 200 |
| `GET` | `/api/v1/tests/{test_id}` | Signed in | 200 |
| `POST` | `/api/v1/tests` | Admin | 201 |
| `PUT` | `/api/v1/tests/{test_id}` | Admin | 200 |
| `DELETE` | `/api/v1/tests/{test_id}` | Admin | 204 |
| `POST` | `/api/v1/centres/{centre_id}/tests` | Admin | 201 |
| `GET` | `/api/v1/centres/{centre_id}/tests` | Signed in | 200 |
| `POST` | `/api/v1/bookings` | Signed in | 201 |
| `GET` | `/api/v1/bookings` | Signed in | 200 |
| `GET` | `/api/v1/bookings/{booking_id}` | Owner or admin | 200 |
| `PATCH` | `/api/v1/bookings/{booking_id}/cancel` | Owner or admin | 200 |
| `POST` | `/api/v1/payments` | Booking owner | 201 |
| `GET` | `/api/v1/payments/{payment_id}` | Owner or admin | 200 |
| `POST` | `/api/v1/payments/webhook` | Provider callback | 200 |

List endpoints for centres, tests, and bookings accept `page` and `limit`. `page` is at least 1. `limit` is from 1 to 100 and defaults to 20. The body is `{ "items", "page", "limit", "total" }`. Centre offerings return a list for that centre, not a page.

Write requests reject unknown fields. A booking may include `amount`, and that value is ignored.

Send the access token as `Authorization: Bearer <token>`.

## 10. Authentication flow

Signup accepts `name`, `email`, and `password`. The password must be at least 8 characters. The email is stored in lowercase. The role is always `USER`. A duplicate email returns 409. The response never includes the password or the hash.

Login accepts email and password. An unknown email and a wrong password both return 401 with `Invalid email or password`. A match returns:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The token is an HS256 JWT. The subject is the user id. The lifetime comes from `ACCESS_TOKEN_EXPIRE_MINUTES`. `GET /api/v1/auth/me` loads that user. A missing, expired, tampered, or unknown token returns 401.

## 11. Booking flow

1. An admin creates a centre and a test, then attaches the test to the centre with a price.
2. A signed-in user posts a centre id, a test id, and a future appointment.
3. The service checks that both records exist and that the centre offers the test.
4. The amount is copied from `centre_tests`. A client-supplied amount does not change it.
5. The booking is saved as `PENDING`.
6. The same user cannot hold a second `PENDING` or `CONFIRMED` booking for that centre, test, and appointment.
7. The owner or an admin can cancel a `PENDING` booking. The slot can be booked again after cancellation.
8. The owner sees only their bookings. An admin sees every booking. Another user receives 403 for a booking they do not own. A missing booking returns 404.

## 12. Payment flow

`POST /api/v1/payments` accepts `{ "booking_id": "<uuid>" }`.

The booking is locked, then the service checks that it exists, belongs to the signed-in user, is still `PENDING`, and has no payment yet. An admin cannot pay for someone else's booking. The amount is copied from the booking.

The simulated result is chosen at random: `SUCCESS` or `FAILED`. Success confirms the booking. Failure marks the booking as failed. The payment row stores a unique `PAY-` reference and a provider transaction id. Both rows are committed together. The response omits the provider transaction id.

A cancelled booking, a booking that is no longer pending, or a second payment returns 409.

## 13. Webhook flow

`POST /api/v1/payments/webhook` does not use a user token. The body is:

```json
{
  "payment_reference": "PAY-1234567890AB",
  "status": "SUCCESS",
  "provider_transaction_id": "TXN-1234567890AB"
}
```

`status` must be `SUCCESS` or `FAILED`. The payment and its booking are locked. A matching status is returned again without changing the row, so a repeated event is safe. `SUCCESS` is not changed to `FAILED`. A failed payment can be updated to success, and the booking is confirmed in the same transaction. A provider transaction id that already belongs to another payment returns 409. An unknown reference returns 404.

## 14. Business rules

- Catalogue reads require a signed-in user. Writes require an admin.
- Centre identity is the name plus the location. The same name may exist in two locations.
- Test names are unique. Price lives only on the centre offering and must be greater than 0.
- The appointment must be in the future. A naive timestamp is UTC.
- One active booking occupies a user, centre, test, and appointment. `CANCELLED` and `FAILED` free the slot.
- Cancel only while the booking is `PENDING`. Confirmed, failed, and already cancelled bookings return 409.
- Cancelled bookings cannot be paid. Only the booking owner can create the payment.
- A booking has one payment. The client does not choose the outcome.
- Webhook replay of the same status is a no-op. A successful payment stays successful if a later event says it failed.

## 15. Error handling

| Status | When |
| --- | --- |
| 400 | The centre does not offer the test, or the appointment is not in the future |
| 401 | Missing or invalid token, or wrong login |
| 403 | A non-admin tried to manage the catalogue, or a user tried to read, cancel, or pay for someone else's record |
| 404 | The centre, test, booking, or payment does not exist |
| 409 | Duplicate email, centre, test, offering, or active slot. Also illegal cancel, illegal payment, and a webhook conflict |
| 422 | Invalid body, unknown field, bad UUID, or a page or limit outside the allowed range |

Clients receive a `detail` message. Database errors and stack traces are not returned. Unhandled conflicts on unique payment data become 409.

## 16. Testing

Postgres must be running and `DATABASE_URL` in `.env` must point at it.

```bash
pytest
```

The suite covers signup, login, tokens, password hashing, catalogue permissions, offerings, booking rules, cancellation, payments, webhook replay and conflicts, and the admin command. Payment tests replace the random outcome so success and failure are deterministic.

## 17. Example API requests

Set a token after login:

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"John Doe\",\"email\":\"john@example.com\",\"password\":\"StrongPassword123\"}"

curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"john@example.com\",\"password\":\"StrongPassword123\"}"

curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Admin catalogue and a booking:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/centres \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"North Lab\",\"location\":\"Pune\"}"

curl -X POST http://127.0.0.1:8000/api/v1/tests \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Complete blood count\",\"description\":\"Standard blood panel\"}"

curl -X POST http://127.0.0.1:8000/api/v1/centres/$CENTRE_ID/tests \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"test_id\":\"$TEST_ID\",\"price\":\"880.00\"}"

curl -X POST http://127.0.0.1:8000/api/v1/bookings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"centre_id\":\"$CENTRE_ID\",\"test_id\":\"$TEST_ID\",\"appointment_at\":\"2027-10-15T10:00:00\",\"amount\":\"1.00\"}"

curl -X POST http://127.0.0.1:8000/api/v1/payments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"booking_id\":\"$BOOKING_ID\"}"

curl -X POST http://127.0.0.1:8000/api/v1/payments/webhook \
  -H "Content-Type: application/json" \
  -d "{\"payment_reference\":\"PAY-1234567890AB\",\"status\":\"SUCCESS\",\"provider_transaction_id\":\"TXN-1234567890AB\"}"
```

The `amount` on the booking request is ignored. The saved amount is `880.00`.



## 18. Design decisions

- The offering table holds the price so two centres can charge different amounts for one test.
- Signup always creates a normal user. Admin accounts are created with a command so a public request cannot grant that role.
- Catalogue reads require login. The assignment allows viewing centres and tests, and this service treats that as a signed-in action.
- The payment result is random inside the service. Tests replace that function. Callers cannot send a flag that forces success.
- The provider transaction id is stored and is not part of the public payment response.
- The webhook is unauthenticated because the assignment describes a provider callback and does not define a signing secret.
- A failed simulated payment still occupies the booking's single payment row. A later success has to arrive on the webhook. A second `POST /payments` is a conflict.
- The active-slot rule is a partial unique index, so cancellation is race-safe.