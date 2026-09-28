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

The `users` table stores name, unique email, password hash, role (`USER` or `ADMIN`), and timestamps. Passwords are hashed with Argon2id before they are stored.
