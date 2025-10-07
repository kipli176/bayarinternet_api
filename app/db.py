from contextlib import asynccontextmanager
import asyncpg 
from typing import Any, List, Optional, Dict

from .config import get_settings
from .utils import serialize_row

settings = get_settings()

pool: Optional[asyncpg.Pool] = None


# --- Pool Management ---
async def connect_db():
    """Inisialisasi koneksi pool ke database (startup)."""
    global pool
    pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=1,
        max_size=10
    )


async def disconnect_db():
    """Tutup koneksi pool (shutdown)."""
    global pool
    if pool:
        await pool.close()
        pool = None


async def _get_pool() -> asyncpg.Pool:
    """Ambil pool atau raise error kalau belum inisialisasi."""
    global pool
    if pool is None:
        raise RuntimeError(
            "Database pool belum diinisialisasi. Pastikan connect_db() dipanggil di startup."
        )
    return pool


# --- Helper Query ---
async def fetch_all(query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    conn_pool = await _get_pool()
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(query, *(params or ()))
        return [serialize_row(dict(r)) for r in rows]


async def fetch_one(query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    conn_pool = await _get_pool()
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(query, *(params or ()))
        return serialize_row(dict(row)) if row else None


async def fetch_val(query: str, params: Optional[tuple] = None) -> Any:
    conn_pool = await _get_pool()
    async with conn_pool.acquire() as conn:
        return await conn.fetchval(query, *(params or ()))


async def execute(query: str, params: Optional[tuple] = None) -> str:
    conn_pool = await _get_pool()
    async with conn_pool.acquire() as conn:
        return await conn.execute(query, *(params or ()))


# --- Transaksi ---
@asynccontextmanager
async def transaction():
    conn_pool = await _get_pool()
    async with conn_pool.acquire() as conn:
        async with conn.transaction():
            yield conn
