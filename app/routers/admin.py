# app/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import json
from app.db import fetch_all, fetch_one, execute
from app.deps import admin_basic_auth
from app.utils import now_tz, send_wa_message

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------
# Resellers
# ---------------------------
@router.get("/resellers")
async def list_resellers(admin=Depends(admin_basic_auth)):
    rows = await fetch_all("SELECT * FROM resellers ORDER BY created_at DESC")
    return {"data": rows, "total": len(rows)}


@router.get("/resellers/{reseller_id}")
async def get_reseller(reseller_id: str, admin=Depends(admin_basic_auth)):
    row = await fetch_one("SELECT * FROM resellers WHERE id=$1", (reseller_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Reseller not found")
    return row


@router.post("/resellers")
async def create_reseller(payload: dict, admin=Depends(admin_basic_auth)):
    sql = """
        INSERT INTO resellers (name, company_name, email, phone, alamat, logo, price_per_user, currency, volume_pricing, password_hash, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
        RETURNING id
    """
    params = (
        payload.get("name"),
        payload.get("company_name"),
        payload.get("email"),
        payload.get("phone"),
        payload.get("alamat"),
        payload.get("logo"),
        payload.get("price_per_user", 0),
        payload.get("currency", "IDR"),
        json.dumps(payload.get("volume_pricing")),
        payload.get("password_hash"),
        now_tz(),
    )
    row = await fetch_one(sql, params)
    return {"id": row["id"]}


@router.put("/resellers/{reseller_id}")
async def update_reseller(reseller_id: str, payload: dict, admin=Depends(admin_basic_auth)):
    set_fields = ", ".join([f"{k}=${i+2}" for i, k in enumerate(payload.keys())])
    sql = f"UPDATE resellers SET {set_fields}, updated_at=${len(payload)+2} WHERE id=$1"
    params = (reseller_id, *payload.values(), now_tz())
    await execute(sql, params)
    return {"message": "Reseller updated"}


@router.delete("/resellers/{reseller_id}")
async def delete_reseller(reseller_id: str, admin=Depends(admin_basic_auth)):
    await execute("DELETE FROM resellers WHERE id=$1", (reseller_id,))
    return {"message": "Reseller deleted"}


# ---------------------------
# Users
# ---------------------------
@router.get("/users")
async def list_users(admin=Depends(admin_basic_auth)):
    rows = await fetch_all(
        "SELECT u.*, r.name AS reseller_name FROM ppp_users u JOIN resellers r ON u.reseller_id=r.id WHERE u.deleted_at IS NULL ORDER BY u.created_at DESC"
    )
    return {"data": rows, "total": len(rows)}


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin=Depends(admin_basic_auth)):
    row = await fetch_one(
        "SELECT u.*, r.name AS reseller_name FROM ppp_users u JOIN resellers r ON u.reseller_id=r.id WHERE u.id=$1",
        (user_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


# ---------------------------
# Invoices
# ---------------------------
@router.get("/invoices")
async def list_customer_invoices(admin=Depends(admin_basic_auth)):
    rows = await fetch_all(
        "SELECT ci.*, r.name AS reseller_name FROM customer_invoices ci JOIN resellers r ON ci.reseller_id=r.id ORDER BY ci.created_at DESC"
    )
    return {"data": rows, "total": len(rows)}


@router.get("/reseller-invoices")
async def list_reseller_invoices(admin=Depends(admin_basic_auth)):
    rows = await fetch_all(
        "SELECT i.*, r.name AS reseller_name FROM invoices i JOIN resellers r ON i.reseller_id=r.id ORDER BY i.created_at DESC"
    )
    return {"data": rows, "total": len(rows)}


@router.post("/reseller-invoices/generate")
async def generate_reseller_invoice(payload: dict, admin=Depends(admin_basic_auth)):
    reseller_id = payload.get("reseller_id")
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    users_count = payload.get("users_count")
    unit_price = payload.get("unit_price")
    subtotal = payload.get("subtotal")
    discount = payload.get("discount", 0)
    tax = payload.get("tax", 0)
    total = payload.get("total")

    sql = """
        INSERT INTO invoices (reseller_id, period_start, period_end, users_count, unit_price, subtotal, discount, tax, total, status, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'unpaid',$10)
        RETURNING id
    """
    row = await fetch_one(sql, (reseller_id, period_start, period_end, users_count, unit_price, subtotal, discount, tax, total, now_tz()))
    return {"id": row["id"], "message": "Reseller invoice generated"}


@router.put("/reseller-invoices/{invoice_id}/pay")
async def mark_reseller_invoice_paid(invoice_id: str, admin=Depends(admin_basic_auth)):
    invoice = await fetch_one(
        "SELECT * FROM invoices WHERE id=$1",
        (invoice_id,),
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice["status"] == "paid":
        raise HTTPException(status_code=400, detail="Invoice already paid")

    paid_at = now_tz()
    await execute(
        "UPDATE invoices SET status='paid', updated_at=$1, meta = jsonb_set(coalesce(meta,'{}'::jsonb),'{$.paid_at}',$2::jsonb,true) WHERE id=$3",
        (paid_at, json.dumps(paid_at.isoformat()), invoice_id),
    )

    reseller_data = await fetch_one("SELECT phone FROM resellers WHERE id=$1", (invoice["reseller_id"],))
    await send_wa_message(
        phone=reseller_data["phone"],
        text=f"Pembayaran invoice reseller {invoice_id} berhasil. Terima kasih."
    )

    row = await fetch_one("SELECT * FROM invoices WHERE id=$1", (invoice_id,))
    # return row

    # await execute(
    #     "UPDATE invoices SET status='paid', paid_at=$1, updated_at=$2 WHERE id=$3",
    #     (now_tz(), now_tz(), invoice_id),
    # )
    return {"message": "Reseller invoice marked as paid"}


# ---------------------------
# Payments
# ---------------------------
@router.get("/payments")
async def list_all_payments(admin=Depends(admin_basic_auth)):
    rows = await fetch_all(
        "SELECT p.*, ci.reseller_id, r.name AS reseller_name FROM payments p JOIN customer_invoices ci ON p.invoice_id=ci.id JOIN resellers r ON ci.reseller_id=r.id ORDER BY p.created_at DESC"
    )
    return {"data": rows, "total": len(rows)}


# ---------------------------
# Reports
# ---------------------------
@router.get("/reports/resellers/summary")
async def summary_resellers(admin=Depends(admin_basic_auth)):
    rows = await fetch_all(
        """
        SELECT r.id, r.name,
            COUNT(u.id) FILTER (WHERE u.deleted_at IS NULL) AS users_count,
            COUNT(ci.id) FILTER (WHERE ci.status='paid') AS invoices_paid,
            COALESCE(SUM(ci.amount) FILTER (WHERE ci.status='paid'),0) AS total_revenue
        FROM resellers r
        LEFT JOIN ppp_users u ON u.reseller_id=r.id
        LEFT JOIN customer_invoices ci ON ci.reseller_id=r.id
        GROUP BY r.id, r.name
        ORDER BY r.name
        """
    )
    return {"resellers": rows}


@router.get("/reports/finance/summary")
async def finance_summary(
    period: Optional[str] = Query(None, description="Format: YYYY-MM"),
    admin=Depends(admin_basic_auth),
):
    params = []
    where_period = ""
    if period:
        params.append(period)
        where_period = "WHERE to_char(ci.period_start,'YYYY-MM')=$1"

    row = await fetch_one(
        f"""
        SELECT
            COUNT(ci.id) FILTER (WHERE ci.status='paid') AS paid_invoices,
            COUNT(ci.id) FILTER (WHERE ci.status!='paid') AS unpaid_invoices,
            COALESCE(SUM(ci.amount) FILTER (WHERE ci.status='paid'),0) AS paid_amount,
            COALESCE(SUM(ci.amount) FILTER (WHERE ci.status!='paid'),0) AS unpaid_amount,
            COALESCE(SUM(p.amount) FILTER (WHERE p.status='success'),0) AS payments_total
        FROM customer_invoices ci
        LEFT JOIN payments p ON p.invoice_id=ci.id
        {where_period}
        """,
        tuple(params),
    )
    return row
