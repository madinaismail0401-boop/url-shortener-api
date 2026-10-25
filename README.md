# URL Shortener API

A small URL-shortening service built with FastAPI, SQLite, and pytest.

## Requirements

- Python 3.10+
- pip

## Setup

```bash
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn app:app --reload
```

Open interactive API documentation at http://127.0.0.1:8000/docs.

The SQLite database (`links.db`) is created automatically. To use another database file, set `DATABASE_PATH` before starting the server.

## Endpoints

### `POST /links`

Create a short link.

Request:
```json
{
  "long_url": "https://example.com/some/long/path",
  "alias": "my-link",
  "expires_at": "2027-01-01T00:00:00Z"
}
```

`alias` and `expires_at` are optional. `expires_at` must be a future ISO-8601 datetime with a timezone. Example response:

```json
{
  "code": "my-link",
  "short_url": "/my-link",
  "long_url": "https://example.com/some/long/path",
  "created_at": "2026-10-25T12:00:00+00:00",
  "expires_at": "2027-01-01T00:00:00+00:00"
}
```

### `GET /{code}`

Redirects to the original URL (HTTP 307). Returns `404` for an unknown code and `410` for an expired link. Successful redirects increment the click count and update `last_clicked_at`.

### `GET /links/{code}/stats`

Returns click statistics:

```json
{
  "code": "my-link",
  "total_clicks": 3,
  "last_clicked_at": "2026-10-25T12:05:00+00:00"
}
```

## Example curl requests

Create a link:
```bash
curl -X POST http://127.0.0.1:8000/links \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com/articles"}'
```

Create a link with an alias and expiry:
```bash
curl -X POST http://127.0.0.1:8000/links \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com","alias":"docs-link","expires_at":"2027-01-01T00:00:00Z"}'
```

Follow a short link without automatically following the redirect:
```bash
curl -i http://127.0.0.1:8000/docs-link
```

Read click statistics:
```bash
curl http://127.0.0.1:8000/links/docs-link/stats
```

## Run tests

```bash
pytest -q
```

The tests cover link creation, redirects and click counts, duplicate aliases, invalid URLs, invalid aliases, unknown links, expired links, and unknown stats requests.
