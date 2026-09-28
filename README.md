# CareLabs

Diagnostic test booking and simulated payment service.

## Local database

Copy the environment file, set real values, then start PostgreSQL:

```bash
copy .env.example .env
docker compose up -d
docker compose ps
```

`docker-compose.yml` reads `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from `.env`. Credentials are not stored in the compose file.

## Migrations

Alembic reads `DATABASE_URL` from `.env`. Apply migrations with:

```bash
alembic upgrade head
```

The `users` table stores name, unique email, password hash, role (`USER` or `ADMIN`), and timestamps. Passwords are hashed with Argon2id before they are stored. Access tokens are signed JWTs. The signing secret comes from `JWT_SECRET`.

`POST /api/v1/auth/signup` creates a normal user. The password must be at least 8 characters. A duplicate email returns 409. Clients cannot choose a role at signup.

`POST /api/v1/auth/login` returns a bearer token. `GET /api/v1/auth/me` requires that token. An unknown email and a wrong password both return 401.

A diagnostic centre has a name, a location, and timestamps. The same name may exist in different locations. The same name and location together must be unique.

A diagnostic test has a unique name, a description, and timestamps. Centre-specific prices are not stored on the test.

`centre_tests` links a centre to a test and stores that centre's price. A centre can offer each test only once. The price must be greater than zero.

Signed-in users can list and fetch diagnostic centres. Only an admin can create, update, or delete them. Lists use `page` and `limit` (maximum 100) and return `items`, `page`, `limit`, and `total`.
