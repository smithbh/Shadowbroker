# Docker Secrets

The backend supports [Docker Swarm secrets](https://docs.docker.com/engine/swarm/secrets/)
so you never have to put API keys in environment variables or `.env` files.

## How it works

At startup (before any service modules are imported), `main.py` checks a
list of secret-capable variables. For each variable `VAR`, if the
environment variable `VAR_FILE` is set (typically `/run/secrets/VAR`),
the file is read, its content is trimmed, and the result is injected into
`os.environ[VAR]`. All downstream code sees a normal environment variable.

## Supported variables

| Variable | Purpose |
|---|---|
| `AIS_API_KEY` | AISStream.io WebSocket key |
| `OPENSKY_CLIENT_ID` | OpenSky Network client ID |
| `OPENSKY_CLIENT_SECRET` | OpenSky Network client secret |
| `LTA_ACCOUNT_KEY` | Singapore LTA DataMall key |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) |

## docker-compose.yml example

```yaml
services:
  backend:
    build:
      context: ./backend
    environment:
      - AIS_API_KEY_FILE=/run/secrets/AIS_API_KEY
      - OPENSKY_CLIENT_ID_FILE=/run/secrets/OPENSKY_CLIENT_ID
      - OPENSKY_CLIENT_SECRET_FILE=/run/secrets/OPENSKY_CLIENT_SECRET
      - LTA_ACCOUNT_KEY_FILE=/run/secrets/LTA_ACCOUNT_KEY
    secrets:
      - AIS_API_KEY
      - OPENSKY_CLIENT_ID
      - OPENSKY_CLIENT_SECRET
      - LTA_ACCOUNT_KEY

secrets:
  AIS_API_KEY:
    file: ./secrets/ais_api_key.txt
  OPENSKY_CLIENT_ID:
    file: ./secrets/opensky_client_id.txt
  OPENSKY_CLIENT_SECRET:
    file: ./secrets/opensky_client_secret.txt
  LTA_ACCOUNT_KEY:
    file: ./secrets/lta_account_key.txt
```

Each secret file should contain only the raw key value (whitespace is trimmed).

## Notes

- The secrets loop runs **before** any FastAPI service imports, so modules
  that read `os.environ` at import time see the injected values.
- Missing or empty secret files log a warning; the backend still starts.
- You can mix approaches: use `_FILE` for some keys and plain env vars for others.
