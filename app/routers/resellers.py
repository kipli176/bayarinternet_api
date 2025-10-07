from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any
from pydantic import BaseModel, EmailStr
from datetime import datetime

from app.utils import ( hash_password, verify_password, create_access_token, create_refresh_token, verify_token, serialize_row )
from app.deps import auth_reseller_jwt
from app.db import fetch_one, execute
from app.utils import new_uuid, now_tz
from app.config import get_settings

settings = get_settings()

router = APIRouter()

# ----------- Schemas -----------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class RegisterResponse(BaseModel):
    id: str
    name: str
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ResellerProfileResponse(BaseModel):
    id: str
    name: str
    company_name: str | None = None
    email: EmailStr
    phone: str | None = None
    alamat: str | None = None
    logo: str | None = None 
    currency: str | None = None
    volume_pricing: Dict[str, Any] | None = None

class ResellerUpdateRequest(BaseModel):
    phone: str | None = None
    alamat: str | None = None
    logo: str | None = None
    company_name: str | None = None

# ----------- Endpoints -----------

@router.post("/auth/register", response_model=RegisterResponse)
async def register(data: RegisterRequest):
    # cek email unik
    existing = await fetch_one("SELECT id FROM resellers WHERE email=$1", (data.email,))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    reseller_id = new_uuid()
    pwd_hash = hash_password(data.password)
    await execute(
        """
        INSERT INTO resellers (id, name, email, password_hash, created_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        (reseller_id, data.name, data.email, pwd_hash, now_tz()),
    )

    return RegisterResponse(id=reseller_id, name=data.name, email=data.email)


@router.post("/auth/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    reseller = await fetch_one(
        "SELECT id, password_hash FROM resellers WHERE email=$1", (data.email,)
    )
    if not reseller or not verify_password(data.password, reseller["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(reseller["id"])
    refresh_token = create_refresh_token(reseller["id"])
    return LoginResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/logout", status_code=204)
async def logout(_: Dict[str, Any] = Depends(auth_reseller_jwt)):
    # opsional: implementasi blacklist token
    return {}


@router.post("/auth/refresh", response_model=RefreshResponse)
async def refresh(data: RefreshRequest):
    payload = verify_token(data.refresh_token, refresh=True)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    new_access = create_access_token(payload["sub"])
    return RefreshResponse(access_token=new_access)


@router.get("/auth/me", response_model=RegisterResponse)
async def auth_me(reseller: Dict[str, Any] = Depends(auth_reseller_jwt)):
    row = await fetch_one(
        "SELECT id, name, email FROM resellers WHERE id=$1",
        (reseller["reseller_id"],),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reseller not found")
    return serialize_row(row)


@router.get("/resellers/me", response_model=ResellerProfileResponse)
async def get_profile(reseller: Dict[str, Any] = Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT id, name, company_name, email, phone, alamat, logo, 
               price_per_user, currency, volume_pricing
        FROM resellers WHERE id=$1
        """,
        (reseller["reseller_id"],),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reseller not found")
    return serialize_row(row)


@router.put("/resellers/me", response_model=ResellerProfileResponse)
async def update_profile(
    data: ResellerUpdateRequest, reseller: Dict[str, Any] = Depends(auth_reseller_jwt)
):
    await execute(
        """
        UPDATE resellers
        SET phone=$1, alamat=$2, logo=$3, updated_at=$4, company_name=$5
        WHERE id=$6
        """,
        (data.phone, data.alamat, data.logo, now_tz(), data.company_name, reseller["reseller_id"]),
    )
    row = await fetch_one(
        """
        SELECT id, name, company_name, email, phone, alamat, logo, 
               price_per_user, currency, volume_pricing
        FROM resellers WHERE id=$1
        """,
        (reseller["reseller_id"],),
    )
    return serialize_row(row)
