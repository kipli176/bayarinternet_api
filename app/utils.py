import bcrypt
import uuid
import json
import httpx
from datetime import datetime, timedelta
import pytz
from jose import jwt, JWTError
from typing import Any, Dict, Optional

from .config import get_settings

settings = get_settings()


# ---- Password Hashing ----
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---- JWT Token ----
def create_access_token(reseller_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_EXPIRES_MIN)
    payload = {"sub": str(reseller_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_refresh_token(reseller_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_REFRESH_EXPIRES_MIN)
    payload = {"sub": str(reseller_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def verify_token(token: str, refresh: bool = False) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        if refresh and payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None



def serialize_row(row: dict) -> dict:
    if not row:
        return row

    result = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)

        # elif k == "volume_pricing" and v is not None:
        elif k in ["meta", "volume_pricing"] and v is not None:
            # Kalau JSON string → parse
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = None

            # Kalau array → ambil elemen pertama
            if isinstance(v, list) and len(v) > 0:
                result[k] = v[0]
            elif isinstance(v, dict):
                result[k] = v
            else:
                result[k] = {}
        else:
            result[k] = v
    return result



# ---- UUID ----
def new_uuid() -> str:
    return str(uuid.uuid4())


# ---- Timezone-aware datetime ----
def now_tz() -> datetime:
    tz = pytz.timezone(settings.TIMEZONE)
    return datetime.now(tz)


# ---- Send WhatsApp Message ----
async def send_wa_message(phone: str, text: str) -> Dict[str, Any]:
    """
    Kirim pesan WA via gateway HTTP.
    Secara otomatis menambahkan kode negara 62 jika belum ada.
    """
    # Normalisasi nomor telepon
    phone = phone.strip().replace("+", "")
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    elif not phone.startswith("62"):
        phone = "62" + phone  # fallback: asumsi tidak pakai kode negara

    print(phone)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.WA_GATEWAY_URL,
                # headers={"Authorization": f"Bearer {settings.WA_TOKEN}"},
                json={"number": phone, "message": text},
            )
            print(settings.WA_GATEWAY_URL)
            print(resp.text)
            return {"status": resp.status_code, "body": resp.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---- Response Helper untuk List ----
def response_list(data: list, page: int, per_page: int, total: int) -> Dict[str, Any]:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "data": data,
    }


# ---- Logging Helper ----
def log_event(event: str, meta: Optional[Dict[str, Any]] = None) -> None:
    ts = now_tz().isoformat()
    print(json.dumps({"time": ts, "event": event, "meta": meta or {}}))
