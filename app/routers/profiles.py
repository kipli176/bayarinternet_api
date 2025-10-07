from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

from app.db import fetch_one, fetch_all, execute
from app.deps import auth_reseller_jwt, pagination
from app.utils import new_uuid, now_tz, response_list

router = APIRouter()

# -------- Schemas --------
class ProfileBase(BaseModel):
    name: str
    price: Decimal

    # Mode teknis
    rate_limit_up: Optional[str] = None
    rate_limit_down: Optional[str] = None
    burst_limit_up: Optional[str] = None
    burst_limit_down: Optional[str] = None
    burst_threshold_up: Optional[str] = None
    burst_threshold_down: Optional[str] = None
    burst_time_up: Optional[int] = None
    burst_time_down: Optional[int] = None
    min_rate_up: Optional[str] = None
    min_rate_down: Optional[str] = None
    priority: Optional[int] = 8

    # Mode group
    group_name: Optional[str] = None
    auto_pool: Optional[bool] = True

    is_active: bool = True


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(ProfileBase):
    pass


class ProfileOut(ProfileBase):
    id: str
    reseller_id: str
    created_at: datetime
    updated_at: datetime


# -------- Endpoints --------

@router.get("/profiles", response_model=Dict[str, Any])
async def list_profiles(
    reseller=Depends(auth_reseller_jwt),
    paging=Depends(pagination),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    conditions = ["reseller_id=$1", "deleted_at IS NULL"]
    params = [reseller["reseller_id"]]

    if is_active is not None:
        conditions.append("is_active=$2")
        params.append(is_active)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT id, reseller_id, name, price,
               rate_limit_up, rate_limit_down, burst_limit_up, burst_limit_down,
               burst_threshold_up, burst_threshold_down, burst_time_up, burst_time_down,
               min_rate_up, min_rate_down, priority, group_name, auto_pool,
               is_active, created_at, updated_at
        FROM ppp_profiles
        WHERE {where_clause}
        ORDER BY created_at DESC
        OFFSET {paging['offset']} LIMIT {paging['limit']}
    """
    rows = await fetch_all(query, tuple(params))

    total = await fetch_one(
        f"SELECT COUNT(*) AS count FROM ppp_profiles WHERE {where_clause}",
        tuple(params),
    )

    return response_list(rows, paging["page"], paging["per_page"], total["count"])


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT id, reseller_id, name, price,
               rate_limit_up, rate_limit_down, burst_limit_up, burst_limit_down,
               burst_threshold_up, burst_threshold_down, burst_time_up, burst_time_down,
               min_rate_up, min_rate_down, priority, group_name, auto_pool,
               is_active, created_at, updated_at
        FROM ppp_profiles
        WHERE id=$1 AND reseller_id=$2 AND deleted_at IS NULL
        """,
        (profile_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


@router.post("/profiles", response_model=ProfileOut)
async def create_profile(data: ProfileCreate, reseller=Depends(auth_reseller_jwt)):
    # Rule: jika group_name kosong, minimal harus ada rate_limit & price
    if not data.group_name and not (data.rate_limit_up and data.rate_limit_down):
        raise HTTPException(status_code=400, detail="Either group_name or rate limits must be provided")

    profile_id = new_uuid()
    await execute(
        """
        INSERT INTO ppp_profiles 
        (id, reseller_id, name, price,
         rate_limit_up, rate_limit_down,
         burst_limit_up, burst_limit_down,
         burst_threshold_up, burst_threshold_down,
         burst_time_up, burst_time_down,
         min_rate_up, min_rate_down,
         priority, group_name, auto_pool,
         is_active, created_at, updated_at)
        VALUES ($1,$2,$3,$4,
                $5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                $15,$16,$17,$18,$19,$20)
        """,
        (
            profile_id,
            reseller["reseller_id"],
            data.name,
            data.price,
            data.rate_limit_up,
            data.rate_limit_down,
            data.burst_limit_up,
            data.burst_limit_down,
            data.burst_threshold_up,
            data.burst_threshold_down,
            data.burst_time_up,
            data.burst_time_down,
            data.min_rate_up,
            data.min_rate_down,
            data.priority,
            data.group_name,
            data.auto_pool,
            data.is_active,
            now_tz(),
            now_tz(),
        ),
    )

    row = await fetch_one(
        """
        SELECT id, reseller_id, name, price,
               rate_limit_up, rate_limit_down, burst_limit_up, burst_limit_down,
               burst_threshold_up, burst_threshold_down, burst_time_up, burst_time_down,
               min_rate_up, min_rate_down, priority, group_name, auto_pool,
               is_active, created_at, updated_at
        FROM ppp_profiles WHERE id=$1
        """,
        (profile_id,),
    )
    return row


@router.put("/profiles/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: str, data: ProfileUpdate, reseller=Depends(auth_reseller_jwt)
):
    await execute(
        """
        UPDATE ppp_profiles
        SET name=$1, price=$2,
            rate_limit_up=$3, rate_limit_down=$4,
            burst_limit_up=$5, burst_limit_down=$6,
            burst_threshold_up=$7, burst_threshold_down=$8,
            burst_time_up=$9, burst_time_down=$10,
            min_rate_up=$11, min_rate_down=$12,
            priority=$13, group_name=$14, auto_pool=$15,
            is_active=$16, updated_at=$17
        WHERE id=$18 AND reseller_id=$19 AND deleted_at IS NULL
        """,
        (
            data.name,
            data.price,
            data.rate_limit_up,
            data.rate_limit_down,
            data.burst_limit_up,
            data.burst_limit_down,
            data.burst_threshold_up,
            data.burst_threshold_down,
            data.burst_time_up,
            data.burst_time_down,
            data.min_rate_up,
            data.min_rate_down,
            data.priority,
            data.group_name,
            data.auto_pool,
            data.is_active,
            now_tz(),
            profile_id,
            reseller["reseller_id"],
        ),
    )

    row = await fetch_one(
        """
        SELECT id, reseller_id, name, price,
               rate_limit_up, rate_limit_down, burst_limit_up, burst_limit_down,
               burst_threshold_up, burst_threshold_down, burst_time_up, burst_time_down,
               min_rate_up, min_rate_down, priority, group_name, auto_pool,
               is_active, created_at, updated_at
        FROM ppp_profiles WHERE id=$1
        """,
        (profile_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, reseller=Depends(auth_reseller_jwt)):
    await execute(
        "DELETE FROM ppp_profiles WHERE id=$1 AND reseller_id=$2",
        (profile_id, reseller["reseller_id"]),
    )
    return {}
