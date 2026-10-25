import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

app = FastAPI(title="URL Shortener API", version="1.0.0")

DB_PATH = os.getenv("DATABASE_PATH", "links.db")
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,30}$")


def utc_now():
    return datetime.now(timezone.utc)


def to_iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def parse_datetime(value):
    """Parse an ISO-8601 datetime, accepting a trailing Z."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="expires_at must be a valid ISO-8601 datetime.")
    if parsed.tzinfo is None:
        raise HTTPException(status_code=400, detail="expires_at must include a timezone, for example +00:00 or Z.")
    return parsed.astimezone(timezone.utc)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS links (
            code TEXT PRIMARY KEY,
            long_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            clicks INTEGER NOT NULL DEFAULT 0,
            last_clicked_at TEXT
        )
    """)
    conn.commit()
    return conn


class CreateLinkRequest(BaseModel):
    long_url: str = Field(..., min_length=1)
    alias: str | None = None
    expires_at: str | None = None


def validate_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="long_url must be a valid absolute HTTP or HTTPS URL."
        )


def row_to_dict(row):
    return {
        "code": row["code"],
        "short_url": f"/{row['code']}",
        "long_url": row["long_url"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


@app.get("/")
def root():
    return {"message": "URL Shortener API", "docs": "/docs"}


@app.post("/links", status_code=201)
def create_link(payload: CreateLinkRequest):
    long_url = payload.long_url.strip()
    validate_url(long_url)

    if payload.alias is not None:
        alias = payload.alias.strip()
        if not ALIAS_PATTERN.fullmatch(alias):
            raise HTTPException(
                status_code=400,
                detail="alias must be 3-30 characters and contain only letters, numbers, hyphens, or underscores."
            )
    else:
        alias = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
        if len(alias) < 3:
            alias = secrets.token_hex(4)

    expiry = parse_datetime(payload.expires_at)
    if expiry and expiry <= utc_now():
        raise HTTPException(status_code=400, detail="expires_at must be in the future.")

    conn = get_connection()
    try:
        if payload.alias is None:
            # Avoid a collision even though generated codes are random.
            while conn.execute("SELECT 1 FROM links WHERE code = ?", (alias,)).fetchone():
                alias = secrets.token_hex(4)
        try:
            conn.execute(
                "INSERT INTO links (code, long_url, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (alias, long_url, to_iso(utc_now()), to_iso(expiry) if expiry else None),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"The alias '{alias}' is already in use.")
        row = conn.execute("SELECT * FROM links WHERE code = ?", (alias,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@app.get("/links/{code}/stats")
def link_stats(code: str):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short link not found.")
        return {
            "code": row["code"],
            "total_clicks": row["clicks"],
            "last_clicked_at": row["last_clicked_at"],
        }
    finally:
        conn.close()


@app.get("/{code}")
def redirect_link(code: str):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short link not found.")

        expiry = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        if expiry and expiry <= utc_now():
            raise HTTPException(status_code=410, detail="This short link has expired.")

        clicked_at = to_iso(utc_now())
        conn.execute(
            "UPDATE links SET clicks = clicks + 1, last_clicked_at = ? WHERE code = ?",
            (clicked_at, code),
        )
        conn.commit()
        return RedirectResponse(url=row["long_url"], status_code=307)
    finally:
        conn.close()
