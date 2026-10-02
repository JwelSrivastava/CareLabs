# CareLabs

CareLabs is a diagnostic booking service. A patient signs in, books a test at a centre, and pays through a simulated provider. An admin maintains centres, tests, and the price each centre charges. The same process serves the HTTP API and the website.


## Requirements

- Python 3.12 or newer for a local virtualenv. The Docker image uses 3.12.
- Docker Desktop with Compose, if you run the stack in containers.
- PostgreSQL 16, either from Compose or already installed on the host.

Pinned packages are in `requirements.txt`: FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic v2, pydantic-settings, psycopg, PyJWT, pwdlib (Argon2id), email-validator, python-dotenv, pytest, and httpx.

## Configuration

Settings come from the environment. The app also reads a `.env` file in the project root. That file is gitignored. Create it before Compose or pytest:

```env
APP_NAME=CareLabs
APP_ENV=local

POSTGRES_USER=carelabs
POSTGRES_PASSWORD=change-me
POSTGRES_DB=carelabs
POSTGRES_PORT=5432

DATABASE_URL=postgresql+psycopg://carelabs:change-me@localhost:5432/carelabs

JWT_SECRET=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

API_PORT=8000

ADMIN_NAME=CareLabs Admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me-admin-password
```

Replace `POSTGRES_PASSWORD`, the password inside `DATABASE_URL`, and `JWT_SECRET` before you run anything. Keep the user, password, database name, and port identical in `POSTGRES_*` and `DATABASE_URL`. Avoid `@`, `:`, `/`, and `#` in the password so the URL stays valid.

`DATABASE_URL` is for tools on the host: pytest, Alembic, and Uvicorn started outside Docker. The API container does not use that URL. Compose builds its own URL with hostname `postgres`.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `APP_NAME` | API | Service name. Default `CareLabs` |
| `APP_ENV` | API | Environment label. Default `local` |
| `POSTGRES_USER` | Postgres container | Database user |
| `POSTGRES_PASSWORD` | Postgres container | Database password |
| `POSTGRES_DB` | Postgres container | Database name |
| `POSTGRES_PORT` | Compose | Host port published for Postgres. Default `5432` |
| `DATABASE_URL` | Host API, Alembic, pytest | SQLAlchemy URL pointing at `localhost` |
| `JWT_SECRET` | API | HMAC secret for access tokens. Required |
| `JWT_ALGORITHM` | API | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | API | Access token lifetime. Default `60` |
| `API_PORT` | Compose | Host port for the API. Default `8000` |
| `ADMIN_NAME` | Admin command | Display name |
| `ADMIN_EMAIL` | Admin command | Admin email |
| `ADMIN_PASSWORD` | Admin command | Password, 8 to 128 characters |

The admin command rejects the passwords `change-me` and `change-me-admin-password`. Set `ADMIN_PASSWORD` to a real value before you create the admin.

If port 5432 is already taken on the machine, set `POSTGRES_PORT=5433` in `.env` and use that port in `DATABASE_URL` when you want host tools to reach the Compose database.

## Run with Docker

From the project root, with `.env` in place:

```bash
docker compose up --build
```

Compose starts two services:

- `postgres` is `postgres:16-alpine`. Data stays in the `carelabs_postgres_data` volume. The service is healthy when `pg_isready` succeeds.
- `api` is built from the Dockerfile. It waits for a healthy database, runs `alembic upgrade head`, then serves Uvicorn on port 8000. The image runs as user id 10001. The `web` directory is mounted read-only, so site edits show up without a rebuild.

```bash
docker compose ps
docker compose logs api
docker compose down
```

`docker compose down` keeps the database volume. `docker compose down -v` deletes it.

Check the API:

```bash
curl http://127.0.0.1:8000/health
```

A healthy process returns `{"status":"ok"}`.

## Run on the host

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate`.

Start only Postgres, apply migrations, then run the app:

```bash
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload
```

Alembic reads `DATABASE_URL` from the environment. The URL written in `alembic.ini` is unused.

```bash
alembic downgrade -1
alembic history
```

The API container runs `alembic upgrade head` on startup, so a Compose-only setup does not need a separate migration command.

## Website

The site is static HTML, CSS, and JavaScript in `web/`. FastAPI serves it at `/ui`. The browser talks to `/api/v1` on the same origin, so no CORS setup is required.

The access token is kept in `sessionStorage` under `carelabs_token`. Closing the tab signs the user out.

| Section | Who | What it does |
| --- | --- | --- |
| Book a test | Signed-in patient | Lists centres and the tests that centre offers, shows the centre’s price, and books a future appointment. The time you pick is sent with your local offset. |
| Appointments | Signed-in patient | Lists that user’s bookings. A pending booking can be paid or cancelled. |
| Account | Anyone | Sign in, create an account, or sign out. Signup always creates a normal user. |
| Manage | Admin | Add a centre, add a test, and set the price that centre charges for a test. Hidden for everyone else. |

Until you sign in, the booking fields stay disabled. Catalogue routes require a token, so an empty dropdown while signed out means the request was not sent. After sign-in, the lists show the centres and tests in the database.

Actions such as booking, payment, cancel, and sign-in show a short notice at the bottom of the page. Payment on the site is the same simulated call as `POST /api/v1/payments`: the result is paid or failed, and no card is charged.

## Admin account

Signup cannot choose a role. Create the first admin with the command below, after the database is migrated and `ADMIN_NAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` are set to real values:

```powershell
$env:ADMIN_NAME = "Ada Admin"
$env:ADMIN_EMAIL = "ada@example.com"
$env:ADMIN_PASSWORD = "replace-with-a-long-password"
python -m app.scripts.create_admin
```

The command prints `created`, `promoted`, or `exists`, plus the email. It does not print the password.

- `created` means a new admin was inserted.
- `promoted` means an existing user with that email was given the admin role and kept the current password.
- `exists` means that email is already an admin, and the command changed nothing.

Inside the API container, when those three variables are present in the environment Compose passed in:

```bash
docker compose exec api python -m app.scripts.create_admin
```

Use a normal email domain such as `example.com`. The address checker rejects some reserved suffixes.

## API

All versioned routes are under `/api/v1`. Send the access token as `Authorization: Bearer <token>`.

| Method | Path | Who | Success |
| --- | --- | --- | --- |
| `GET` | `/health` | Public | 200 |
| `GET` | `/` | Public | 307 to `/ui/` |
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

List endpoints for centres, tests, and bookings take `page` and `limit`. `page` is at least 1. `limit` is from 1 to 100 and defaults to 20. The body is `{ "items", "page", "limit", "total" }`. Offerings for one centre return a list, not a page.

Write bodies reject unknown fields. A booking may include `amount`; that value is ignored and the stored amount is copied from the centre’s price.

Public ids are UUIDs. Responses use a `detail` message. Database errors and stack traces are not returned.

| Status | When |
| --- | --- |
| 400 | The centre does not offer the test, or the appointment is not in the future |
| 401 | Missing or invalid token, or a failed login |
| 403 | A non-admin tried to change the catalogue, or a user opened, cancelled, or paid for someone else’s record |
| 404 | The centre, test, booking, payment, or webhook reference does not exist |
| 409 | Duplicate email, centre, test, offering, or active slot. Also an illegal cancel, a second payment, or a webhook conflict |
| 422 | Invalid body, unknown field, bad UUID, page or limit out of range, or a webhook status of `PENDING` |

## Authentication

Signup accepts `name`, `email`, and `password`. The password is 8 to 128 characters. The email is stored in lowercase. The role is always `USER`. A duplicate email returns 409. The response omits the password and the hash. Passwords are stored as Argon2id hashes.

Login accepts email and password. An unknown email and a wrong password both return 401 with `Invalid email or password`. A match returns:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The token is an HS256 JWT. The subject is the user id. The lifetime is `ACCESS_TOKEN_EXPIRE_MINUTES`. `GET /api/v1/auth/me` loads that user. A missing, expired, tampered, or unknown token returns 401.

## Booking

1. An admin creates a centre and a test, then attaches the test to the centre with a price greater than 0.
2. A signed-in user posts a centre id, a test id, and a future appointment.
3. The service checks that both records exist and that the centre offers the test.
4. The amount is copied from `centre_tests`.
5. The booking is saved as `PENDING`.
6. The same user cannot hold a second `PENDING` or `CONFIRMED` booking for that centre, test, and appointment. `CANCELLED` and `FAILED` free the slot. The rule is a partial unique index.
7. The owner or an admin can cancel while the booking is `PENDING`. Confirmed, failed, and already cancelled bookings return 409.
8. A user lists only their own bookings. An admin lists every booking. Another user’s booking returns 403. A missing booking returns 404.

A timestamp without an offset is treated as UTC. The website sends the local offset so the clock time on the form is the time that is stored.

Booking statuses are `PENDING`, `CONFIRMED`, `FAILED`, and `CANCELLED`.

## Payments

`POST /api/v1/payments` accepts `{ "booking_id": "<uuid>" }`.

The booking is locked. It must exist, belong to the signed-in user, still be `PENDING`, and have no payment yet. An admin cannot pay for someone else’s booking. The amount is copied from the booking.

The simulated result is `SUCCESS` or `FAILED`, chosen at random inside the service. Success confirms the booking. Failure marks the booking as failed. The payment stores a unique `PAY-` reference and a provider transaction id. Both rows commit together. The API response omits `provider_transaction_id`.

A cancelled booking, a booking that is no longer pending, or a second payment returns 409. A failed charge still uses the booking’s only payment row. A later success has to arrive on the webhook.

Payment statuses are `PENDING`, `SUCCESS`, and `FAILED`. A new simulated charge is written as `SUCCESS` or `FAILED` immediately.

### Webhook

`POST /api/v1/payments/webhook` does not use a user token.

```json
{
  "payment_reference": "PAY-1234567890AB",
  "status": "SUCCESS",
  "provider_transaction_id": "TXN-1234567890AB"
}
```

`status` must be `SUCCESS` or `FAILED`. The payment and its booking are locked. The same status is returned again without a change. `SUCCESS` is not overwritten by `FAILED`. A failed payment can become `SUCCESS`, and the booking is confirmed in that same transaction. A provider transaction id that already belongs to another payment returns 409. An unknown reference returns 404.

## Data

| Table | Purpose | Constraints |
| --- | --- | --- |
| `users` | Accounts | Unique email. Role `USER` or `ADMIN` |
| `diagnostic_centres` | Labs | Unique pair of name and location |
| `diagnostic_tests` | Test catalogue | Unique name. Price is not stored here |
| `centre_tests` | A test offered by one centre | Unique `(centre_id, test_id)`. Price greater than 0, up to 10 digits and 2 decimal places. Deleting a centre or test deletes its offerings |
| `bookings` | An appointment | Amount greater than 0. One active booking per user, centre, test, and appointment. Foreign keys restrict deletion of the user, centre, and test |
| `payments` | One charge for a booking | Unique `booking_id`, unique `payment_reference`, unique `provider_transaction_id` when set. Amount greater than 0 |

Migrations live in `alembic/versions` and create users, centres, tests, offerings, bookings, and payments.

## Example requests

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"John Doe\",\"email\":\"john@example.com\",\"password\":\"StrongPassword123\"}"

curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"john@example.com\",\"password\":\"StrongPassword123\"}"
```

Use the token from login as `$TOKEN`, and an admin token as `$ADMIN_TOKEN`:

```bash
curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

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
  -d "{\"centre_id\":\"$CENTRE_ID\",\"test_id\":\"$TEST_ID\",\"appointment_at\":\"2027-10-15T10:00:00+00:00\"}"

curl -X POST http://127.0.0.1:8000/api/v1/payments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"booking_id\":\"$BOOKING_ID\"}"
```

The saved booking amount is `880.00`, the price on the offering.

## Tests

Postgres must be running, and `DATABASE_URL` in `.env` must point at it. Host pytest does not use the Compose hostname `postgres`.

```bash
pytest
```

`pytest.ini` sets `pythonpath = .` and `testpaths = tests`. The suite covers passwords, tokens, signup, login, centres, tests, offerings, booking access and cancellation, payments, webhook conflicts, and the admin command. Payment tests replace the random outcome so success and failure are fixed.

## Project layout

```text
app/
  main.py                 FastAPI app, /health, redirect to /ui
  api/routes/             auth, centres, tests, bookings, payments
  api/deps.py             current user and admin checks
  core/                   settings, database session, password and JWT helpers
  models/                 users, centres, tests, offerings, bookings, payments
  schemas/                request and response models
  services/               booking and payment rules, one transaction where they change together
  repositories/           user lookup by email
  scripts/create_admin.py admin account command
alembic/                  migrations
web/                      booking site (index.html, styles.css, app.js)
tests/                    pytest suite
Dockerfile                API image
docker-compose.yml        Postgres and API
requirements.txt          pinned Python packages
```

Routes validate input and map service errors to status codes. Services own the booking and payment rules. Models own the schema.
