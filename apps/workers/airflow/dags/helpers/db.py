"""AuraFlow Airflow — Database Helpers

Synchronous psycopg2 connections for Airflow tasks.
Airflow uses sync execution, so we can't use the asyncpg-based
session module from the FastAPI app.
"""
import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

_SAFE_SCHEMA_RE = re.compile(r"^(af_tenant_[a-z0-9_]+|af_global|public)$")


def _validate_schema(name: str) -> str:
    """Validate schema name to prevent SQL injection."""
    if not _SAFE_SCHEMA_RE.match(name):
        raise ValueError(f"Invalid schema name: {name}")
    return name

DATABASE_URL = os.environ.get(
    "AURAFLOW_DATABASE_URL",
    "postgresql://auraflow:auraflow_dev@localhost/auraflow",
)


@contextmanager
def get_global_conn():
    """Connection with search_path set to af_global."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SET search_path TO af_global, public")
        yield conn
    finally:
        conn.close()


@contextmanager
def get_tenant_conn(schema_name: str):
    """Connection with search_path set to a tenant schema."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = False
        schema_name = _validate_schema(schema_name)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f'SET search_path TO "{schema_name}", public')
        yield conn
    finally:
        conn.close()


def fetch_all(conn, query: str, params=None) -> list:
    """Execute a query and return all rows as dicts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(conn, query: str, params=None) -> dict | None:
    """Execute a query and return a single row as dict, or None."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(conn, query: str, params=None):
    """Execute a query (INSERT/UPDATE/DDL) and commit."""
    with conn.cursor() as cur:
        cur.execute(query, params)
    conn.commit()
