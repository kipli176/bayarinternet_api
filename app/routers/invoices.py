from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, timedelta, datetime
from decimal import Decimal
import json

from app.db import fetch_one, fetch_all, execute
from app.deps import auth_reseller_jwt, pagination
from app.utils import new_uuid, now_tz, response_list, send_wa_message

router = APIRouter()


# ---------- Schemas ----------
class CustomerInvoiceCreate(BaseModel):
    user_id: str
    months: int = 1


class CustomerInvoiceOut(BaseModel):
    id: str
    reseller_id: str
    user_id: str
    profile_id: str
    period_start: date
    period_end: date
    amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime]
    meta: Optional[Dict[str, Any]]


class ResellerInvoiceOut(BaseModel):
    id: str
    reseller_id: str
    period_start: datetime
    period_end: datetime
    users_count: int
    unit_price: Decimal
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime
    meta: Optional[Dict[str, Any]]


# ---------- Customer Invoices ----------
@router.post("/invoices", response_model=CustomerInvoiceOut)
async def create_customer_invoice(data: CustomerInvoiceCreate, reseller=Depends(auth_reseller_jwt)):
    user = await fetch_one(
        "SELECT id, username, full_name, phone, profile_id, active_until FROM ppp_users WHERE id=$1 AND reseller_id=$2",
        (data.user_id, reseller["reseller_id"]),
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await fetch_one(
        "SELECT id, name, price FROM ppp_profiles WHERE id=$1",
        (user["profile_id"],),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    start_from = user["active_until"] or date.today()
    period_start = start_from + timedelta(days=1)
    period_end = period_start + timedelta(days=30 * data.months) - timedelta(days=1)

    # cek duplikat invoice user untuk periode ini
    existing = await fetch_one(
        "SELECT * FROM customer_invoices WHERE user_id=$1 AND period_start=$2 AND period_end=$3",
        (user["id"], period_start, period_end),
    )
    if existing:
        return existing  # ✅ kembalikan invoice lama

    amount = profile["price"] * data.months

    meta = {
        "username": user["username"],
        "full_name": user["full_name"],
        "phone": user["phone"],
        "profile_name": profile["name"],
        "unit_price": str(profile["price"]),
        "months": data.months
    }

    invoice_id = new_uuid()
    await execute(
        """
        INSERT INTO customer_invoices
        (id, reseller_id, user_id, profile_id, period_start, period_end, amount, status, meta, created_at, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,'unpaid',$8::jsonb,$9,$10)
        """,
        (
            invoice_id,
            reseller["reseller_id"],
            user["id"],
            profile["id"],
            period_start,
            period_end,
            amount,
            json.dumps(meta),
            now_tz(),
            now_tz(),
        ),
    )

    await send_wa_message(
        phone=user.get("phone"),
        text=f"Tagihan baru {data.months} bulan paket {profile['name']} total {amount} jatuh tempo {period_end}."
    )

    row = await fetch_one("SELECT * FROM customer_invoices WHERE id=$1", (invoice_id,))
    return row

from fastapi import Query

@router.get("/invoices", response_model=Dict[str, Any])
async def list_customer_invoices(
    reseller=Depends(auth_reseller_jwt),
    paging=Depends(pagination),
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    period: Optional[str] = None,  # format YYYY-MM
    search: Optional[str] = Query(None, description="Cari berdasarkan full_name"),
):
    conditions = ["ci.reseller_id=$1"]
    params = [reseller["reseller_id"]]
    idx = 2

    if user_id:
        conditions.append(f"ci.user_id=${idx}")
        params.append(user_id)
        idx += 1

    if status:
        conditions.append(f"ci.status=${idx}")
        params.append(status)
        idx += 1

    if period:
        conditions.append(f"to_char(ci.period_start, 'YYYY-MM')=${idx}")
        params.append(period)
        idx += 1

    if search:
        conditions.append(f"u.full_name ILIKE ${idx}")
        params.append(f"%{search}%")
        idx += 1

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            ci.*, 
            u.full_name
        FROM customer_invoices ci
        JOIN ppp_users u ON ci.user_id = u.id
        WHERE {where_clause}
        ORDER BY ci.created_at DESC
        OFFSET {paging['offset']} LIMIT {paging['limit']}
    """
    rows = await fetch_all(query, tuple(params))

    total = await fetch_one(
        f"""
        SELECT COUNT(*) AS count
        FROM customer_invoices ci
        JOIN ppp_users u ON ci.user_id = u.id
        WHERE {where_clause}
        """,
        tuple(params),
    )

    return response_list(rows, paging["page"], paging["per_page"], total["count"])


@router.get("/invoices/{invoice_id}", response_model=CustomerInvoiceOut)
async def get_customer_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        "SELECT * FROM customer_invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return row

@router.put("/invoices/{invoice_id}/pay", response_model=CustomerInvoiceOut)
async def pay_customer_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    invoice = await fetch_one(
        "SELECT * FROM customer_invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice["status"] == "paid":
        raise HTTPException(status_code=400, detail="Invoice already paid")

    paid_at = now_tz()
    await execute(
        "UPDATE customer_invoices SET status='paid', paid_at=$1, updated_at=$2 WHERE id=$3",
        (paid_at, now_tz(), invoice_id),
    )

    # extend active_until user
    user = await fetch_one("SELECT id, active_until, phone FROM ppp_users WHERE id=$1", (invoice["user_id"],))
    current_until = user["active_until"] or invoice["period_start"]
    new_until = current_until + (invoice["period_end"] - invoice["period_start"]) + timedelta(days=1)
    await execute("UPDATE ppp_users SET active_until=$1 WHERE id=$2", (new_until, user["id"]))

    # insert ke payments
    await execute(
        """
        INSERT INTO payments (invoice_id, amount, method, status, paid_at, created_at)
        VALUES ($1,$2,'manual','success',$3,$4)
        """,
        (invoice_id, invoice["amount"], paid_at, now_tz()),
    )

    await send_wa_message(
        phone=user["phone"],
        text=f"Pembayaran invoice {invoice_id} berhasil. Layanan aktif sampai {new_until}."
    )

    row = await fetch_one("SELECT * FROM customer_invoices WHERE id=$1", (invoice_id,))
    return row


@router.get("/invoices/{invoice_id}/print")
async def print_customer_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        "SELECT * FROM customer_invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "invoice": row,
        "print_template": "customer_invoice",
        "note": "Gunakan data ini untuk cetak nota customer."
    }


# ---------- Reseller Invoices ----------
# GET /reseller-invoices/me?status=unpaid&year=2025&month=10

@router.get("/reseller-invoices/me", response_model=Dict[str, Any])
async def list_my_reseller_invoices(
    reseller=Depends(auth_reseller_jwt),
    paging=Depends(pagination),
    status: Optional[str] = Query(None, description="Filter status invoice (paid/unpaid/draft)"),
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
    month: Optional[int] = Query(None, description="Filter bulan (1-12)"),
):
    """
    🔹 Ambil daftar invoice milik reseller yang sedang login.
    Mirip list_reseller_invoices tapi otomatis pakai reseller_id dari token.
    """
    conditions = ["reseller_id=$1"]
    params = [reseller["reseller_id"]]
    idx = 2

    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    # filter tahun dan bulan opsional
    if year:
        conditions.append(f"EXTRACT(YEAR FROM period_start)=${idx}")
        params.append(year)
        idx += 1
    if month:
        conditions.append(f"EXTRACT(MONTH FROM period_start)=${idx}")
        params.append(month)
        idx += 1

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            id, reseller_id, period_start, period_end, users_count, unit_price,
            subtotal, discount, tax, total, currency, status, created_at, updated_at, meta
        FROM invoices
        WHERE {where_clause}
        ORDER BY period_start DESC
        OFFSET {paging['offset']} LIMIT {paging['limit']}
    """

    rows = await fetch_all(query, tuple(params))

    total = await fetch_one(
        f"SELECT COUNT(*) AS count FROM invoices WHERE {where_clause}",
        tuple(params),
    )

    return response_list(rows, paging["page"], paging["per_page"], total["count"])


@router.get("/reseller-invoices", response_model=Dict[str, Any])
async def list_reseller_invoices(
    reseller=Depends(auth_reseller_jwt),
    paging=Depends(pagination),
    status: Optional[str] = Query(None, description="Filter status invoice (paid/unpaid/draft)"),
    year: Optional[int] = Query(None, description="Tahun periode (YYYY)"),
    month: Optional[int] = Query(None, description="Bulan periode (1-12)")
):
    conditions = ["reseller_id=$1"]
    params = [reseller["reseller_id"]]

    # Dynamic param index (biar fleksibel)
    idx = 2
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    if year and month:
        from datetime import date, timedelta
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)
        conditions.append(f"period_start=$${idx} AND period_end=$${idx+1}")
        params.extend([period_start, period_end])
        idx += 2

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT *
        FROM invoices
        WHERE {where_clause}
        ORDER BY created_at DESC
        OFFSET {paging['offset']} LIMIT {paging['limit']}
    """
    rows = await fetch_all(query, tuple(params))

    total = await fetch_one(
        f"SELECT COUNT(*) AS count FROM invoices WHERE {where_clause}",
        tuple(params),
    )

    return response_list(rows, paging["page"], paging["per_page"], total["count"])

@router.get("/reseller-invoices/{invoice_id}", response_model=ResellerInvoiceOut)
async def get_reseller_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT id, reseller_id, period_start, period_end,
               users_count, unit_price, subtotal, discount, tax, total,
               currency, status, created_at, updated_at, meta
        FROM invoices
        WHERE id=$1 AND reseller_id=$2
        """,
        (invoice_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reseller invoice not found")
    return row

@router.post("/reseller-invoices/generate", response_model=ResellerInvoiceOut)
async def generate_reseller_invoice(
    reseller=Depends(auth_reseller_jwt),
    year: Optional[int] = Query(None, description="Tahun periode (YYYY)"),
    month: Optional[int] = Query(None, description="Bulan periode (1-12)")
):
    today = date.today()

    # tentukan periode
    if year and month:
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Bulan harus 1-12")
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)
    else:
        # default bulan ini
        period_start = date(today.year, today.month, 1)
        if today.month == 12:
            period_end = date(today.year, 12, 31)
        else:
            period_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # cek duplikat invoice
    existing = await fetch_one(
        "SELECT id FROM invoices WHERE reseller_id=$1 AND period_start=$2 AND period_end=$3",
        (reseller["reseller_id"], period_start, period_end),
    )
    if existing:
        raise HTTPException(status_code=400, detail="Invoice already exists for this period")

    # hitung jumlah user aktif
    users_count = await fetch_one(
        "SELECT COUNT(*) FROM ppp_users WHERE reseller_id=$1 AND status='active' AND deleted_at IS NULL",
        (reseller["reseller_id"],),
    )

    reseller_data = await fetch_one(
        "SELECT name, company_name, phone, price_per_user, currency FROM resellers WHERE id=$1",
        (reseller["reseller_id"],),
    )

    unit_price = reseller_data["price_per_user"]
    subtotal = unit_price * users_count["count"]
    total = subtotal

    meta = {
        "reseller_name": reseller_data["name"],
        "company": reseller_data["company_name"],
        "phone": reseller_data["phone"],
        "unit_price": str(unit_price),
        "users_count": users_count["count"]
    }

    invoice_id = new_uuid()
    await execute(
        """
        INSERT INTO invoices
        (id, reseller_id, period_start, period_end, users_count, unit_price, subtotal, discount, tax, total, currency, status, meta, created_at, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,0,0,$7,$8,'unpaid',$9,$10,$11)
        """,
        (
            invoice_id,
            reseller["reseller_id"],
            period_start,
            period_end,
            users_count["count"],
            unit_price,
            subtotal,
            reseller_data["currency"],
            json.dumps(meta),
            now_tz(),
            now_tz(),
        ),
    )

    await send_wa_message(
        phone=reseller_data["phone"],
        text=f"Invoice reseller periode {period_start} - {period_end} total {total}, due date {period_end.replace(day=20)}."
    )

    row = await fetch_one("SELECT * FROM invoices WHERE id=$1", (invoice_id,))
    return row




@router.put("/reseller-invoices/{invoice_id}/pay", response_model=ResellerInvoiceOut)
async def pay_reseller_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    invoice = await fetch_one(
        "SELECT * FROM invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
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

    reseller_data = await fetch_one("SELECT phone FROM resellers WHERE id=$1", (reseller["reseller_id"],))
    await send_wa_message(
        phone=reseller_data["phone"],
        text=f"Pembayaran invoice reseller {invoice_id} berhasil. Terima kasih."
    )

    row = await fetch_one("SELECT * FROM invoices WHERE id=$1", (invoice_id,))
    return row


@router.get("/reseller-invoices/{invoice_id}/print")
async def print_reseller_invoice(invoice_id: str, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        "SELECT * FROM invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reseller invoice not found")
    return {
        "invoice": row,
        "print_template": "reseller_invoice",
        "note": "Gunakan data ini untuk cetak nota reseller."
    }
