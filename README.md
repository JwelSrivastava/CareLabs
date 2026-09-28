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
