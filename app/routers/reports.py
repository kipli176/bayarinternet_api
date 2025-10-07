# app/routers/reports.py
from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.db import fetch_one, fetch_all
from app.deps import auth_reseller_jwt

router = APIRouter(tags=["Reports"])


# ---------------------------
# GET /reports/users/summary
# ---------------------------
@router.get("/reports/users/summary")
async def users_summary(reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT 
            COUNT(*) FILTER (WHERE status='active' AND deleted_at IS NULL) AS active,
            COUNT(*) FILTER (WHERE status='suspended' AND deleted_at IS NULL) AS suspended,
            COUNT(*) FILTER (WHERE deleted_at IS NULL) AS total
        FROM ppp_users
        WHERE reseller_id=$1
        """,
        (reseller["reseller_id"],),
    )
    return row


# ---------------------------
# GET /reports/invoices/summary
# ---------------------------
@router.get("/reports/invoices/summary")
async def invoices_summary(
    period: Optional[str] = Query(None, description="Format: YYYY-MM"),
    reseller=Depends(auth_reseller_jwt),
):
    params = [reseller["reseller_id"]]
    where_period = ""
    if period:
        params.append(period)
        where_period = "AND to_char(period_start,'YYYY-MM')=$2"

    row = await fetch_one(
        f"""
        SELECT 
            COUNT(*) FILTER (WHERE status='paid') AS paid_count,
            COALESCE(SUM(amount) FILTER (WHERE status='paid'),0) AS paid_amount,
            COUNT(*) FILTER (WHERE status!='paid') AS unpaid_count,
            COALESCE(SUM(amount) FILTER (WHERE status!='paid'),0) AS unpaid_amount
        FROM customer_invoices
        WHERE reseller_id=$1 {where_period}
        """,
        tuple(params),
    )
    return row


# ---------------------------
# GET /reports/payments/summary
# ---------------------------
@router.get("/reports/payments/summary")
async def payments_summary(
    period: Optional[str] = Query(None, description="Format: YYYY-MM"),
    reseller=Depends(auth_reseller_jwt),
):
    params = [reseller["reseller_id"]]
    where_period = ""
    if period:
        params.append(period)
        where_period = "AND to_char(p.created_at,'YYYY-MM')=$2"

    rows = await fetch_all(
        f"""
        SELECT p.method, COUNT(p.id) AS count, SUM(p.amount) AS total
        FROM payments p
        JOIN customer_invoices ci ON ci.id = p.invoice_id
        WHERE ci.reseller_id=$1 {where_period}
        GROUP BY p.method
        """,
        tuple(params),
    )

    return {"methods": rows}


# ---------------------------
# GET /reports/profiles/summary
# ---------------------------
@router.get("/reports/profiles/summary")
async def profiles_summary(reseller=Depends(auth_reseller_jwt)):
    rows = await fetch_all(
        """
        SELECT 
            pr.id, pr.name, 
            COUNT(u.id) FILTER (WHERE u.deleted_at IS NULL) AS users_count,
            COALESCE(SUM(ci.amount) FILTER (WHERE ci.status='paid'),0) AS total_revenue
        FROM ppp_profiles pr
        LEFT JOIN ppp_users u ON u.profile_id=pr.id AND u.reseller_id=pr.reseller_id
        LEFT JOIN customer_invoices ci ON ci.profile_id=pr.id AND ci.reseller_id=pr.reseller_id
        WHERE pr.reseller_id=$1 AND pr.deleted_at IS NULL
        GROUP BY pr.id, pr.name
        ORDER BY pr.name
        """,
        (reseller["reseller_id"],),
    )
    return {"profiles": rows}
