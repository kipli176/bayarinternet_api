from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import date, datetime

from app.db import fetch_one, fetch_all, execute
from app.deps import auth_reseller_jwt, pagination
from app.utils import new_uuid, now_tz, response_list

router = APIRouter()

# -------- Schemas --------
class UserBase(BaseModel):
    username: str
    password: str   # akan disimpan langsung ke kolom password_hash
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    alamat: Optional[str] = None
    profile_id: Optional[str] = None
    active_until: Optional[date] = None
    status: Optional[str] = "active"   # active/suspended
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    alamat: Optional[str] = None
    profile_id: Optional[str] = None
    active_until: Optional[date] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: str
    reseller_id: str
    username: str
    full_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    alamat: Optional[str]
    profile_id: Optional[str]
    status: str
    active_until: Optional[date]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# -------- Endpoints --------

@router.get("/users", response_model=Dict[str, Any])
async def list_users(
    reseller=Depends(auth_reseller_jwt),
    paging=Depends(pagination),
    status: Optional[str] = None,
    profile_id: Optional[str] = None,
    search: Optional[str] = None,
):
    conditions = ["reseller_id=$1", "deleted_at IS NULL"]
    params = [reseller["reseller_id"]]

    if status:
        conditions.append(f"status=${len(params)+1}")
        params.append(status)

    if profile_id:
        conditions.append(f"profile_id=${len(params)+1}")
        params.append(profile_id)

    if search:
        conditions.append(f"(username ILIKE ${len(params)+1} OR full_name ILIKE ${len(params)+1})")
        params.append(f"%{search}%")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT id, reseller_id, username, full_name, phone, email, alamat, profile_id,
               status, active_until, is_active, created_at, updated_at
        FROM ppp_users
        WHERE {where_clause}
        ORDER BY created_at DESC
        OFFSET {paging['offset']} LIMIT {paging['limit']}
    """
    rows = await fetch_all(query, tuple(params))

    total = await fetch_one(
        f"SELECT COUNT(*) AS count FROM ppp_users WHERE {where_clause}", tuple(params)
    )

    return response_list(rows, paging["page"], paging["per_page"], total["count"])


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT id, reseller_id, username, full_name, phone, email, alamat, profile_id,
               status, active_until, is_active, created_at, updated_at
        FROM ppp_users
        WHERE id=$1 AND reseller_id=$2 AND deleted_at IS NULL
        """,
        (user_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


@router.post("/users", response_model=UserOut)
async def create_user(data: UserCreate, reseller=Depends(auth_reseller_jwt)):
    user_id = new_uuid()

    await execute(
        """
        INSERT INTO ppp_users
        (id, reseller_id, username, password_hash, full_name, phone, email, alamat,
         profile_id, status, active_until, is_active, created_at, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        """,
        (
            user_id,
            reseller["reseller_id"],
            data.username,
            data.password,  # langsung simpan cleartext
            data.full_name,
            data.phone,
            data.email,
            data.alamat,
            data.profile_id,
            data.status,
            data.active_until,
            data.is_active,
            now_tz(),
            now_tz(),
        ),
    )

    row = await fetch_one(
        """
        SELECT id, reseller_id, username, full_name, phone, email, alamat, profile_id,
               status, active_until, is_active, created_at, updated_at
        FROM ppp_users WHERE id=$1
        """,
        (user_id,),
    )
    return row


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, data: UserUpdate, reseller=Depends(auth_reseller_jwt)):
    old = await fetch_one(
        "SELECT * FROM ppp_users WHERE id=$1 AND reseller_id=$2 AND deleted_at IS NULL",
        (user_id, reseller["reseller_id"]),
    )
    if not old:
        raise HTTPException(status_code=404, detail="User not found")

    await execute(
        """
        UPDATE ppp_users
        SET username=$1, password_hash=$2, full_name=$3, phone=$4, email=$5,
            alamat=$6, profile_id=$7, status=$8, active_until=$9,
            is_active=$10, updated_at=$11
        WHERE id=$12 AND reseller_id=$13
        """,
        (
            data.username or old["username"],
            data.password or old["password_hash"],
            data.full_name or old["full_name"],
            data.phone or old["phone"],
            data.email or old["email"],
            data.alamat or old["alamat"],
            data.profile_id or old["profile_id"],
            data.status or old["status"],
            data.active_until or old["active_until"],
            data.is_active if data.is_active is not None else old["is_active"],
            now_tz(),
            user_id,
            reseller["reseller_id"],
        ),
    )

    row = await fetch_one(
        """
        SELECT id, reseller_id, username, full_name, phone, email, alamat, profile_id,
               status, active_until, is_active, created_at, updated_at
        FROM ppp_users WHERE id=$1
        """,
        (user_id,),
    )
    return row


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, reseller=Depends(auth_reseller_jwt)):
    # Hard delete
    await execute(
        "DELETE FROM ppp_users WHERE id=$1 AND reseller_id=$2",
        (user_id, reseller["reseller_id"]),
    )
    return {}


@router.patch("/users/{user_id}/status", response_model=UserOut)
async def change_status(user_id: str, status: str, reseller=Depends(auth_reseller_jwt)):
    if status not in ["active", "suspended"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    await execute(
        """
        UPDATE ppp_users
        SET status=$1, updated_at=$2
        WHERE id=$3 AND reseller_id=$4 AND deleted_at IS NULL
        """,
        (status, now_tz(), user_id, reseller["reseller_id"]),
    )

    row = await fetch_one(
        """
        SELECT id, reseller_id, username, full_name, phone, email, alamat, profile_id,
               status, active_until, is_active, created_at, updated_at
        FROM ppp_users WHERE id=$1
        """,
        (user_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row
