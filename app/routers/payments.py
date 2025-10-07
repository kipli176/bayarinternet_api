# app/routers/payments.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from app.db import fetch_all, fetch_one, execute
from app.deps import auth_reseller_jwt
from app.utils import now_tz, send_wa_message

router = APIRouter(tags=["Payments"])


# ---------------------------
# GET /payments
# ---------------------------
@router.get("/payments")
async def list_payments(
    invoice_id: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    period: Optional[str] = Query(None),  # YYYY-MM
    search: Optional[str] = Query(None, description="Cari berdasarkan full_name user"),
    reseller=Depends(auth_reseller_jwt),
):
    conditions = ["ci.reseller_id=$1"]
    params = [reseller["reseller_id"]]
    idx = 2

    if invoice_id:
        conditions.append(f"p.invoice_id=${idx}")
        params.append(invoice_id)
        idx += 1
    if method:
        conditions.append(f"p.method=${idx}")
        params.append(method)
        idx += 1
    if status:
        conditions.append(f"p.status=${idx}")
        params.append(status)
        idx += 1
    if period:
        conditions.append(f"to_char(p.created_at, 'YYYY-MM')=${idx}")
        params.append(period)
        idx += 1
    if search:
        conditions.append(f"u.full_name ILIKE ${idx}")
        params.append(f"%{search}%")
        idx += 1

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT 
            p.*, 
            u.full_name
        FROM payments p
        JOIN customer_invoices ci ON p.invoice_id = ci.id
        JOIN ppp_users u ON ci.user_id = u.id
        WHERE {where_clause}
        ORDER BY p.created_at DESC
    """

    rows = await fetch_all(sql, tuple(params))
    return {"data": rows, "total": len(rows)}



# ---------------------------
# GET /payments/{id}
# ---------------------------
@router.get("/payments/{payment_id}")
async def get_payment(payment_id: int, reseller=Depends(auth_reseller_jwt)):
    row = await fetch_one(
        """
        SELECT 
            p.*, 
            u.full_name
        FROM payments p
        JOIN customer_invoices ci ON p.invoice_id = ci.id
        JOIN ppp_users u ON ci.user_id = u.id
        WHERE p.id = $1 AND ci.reseller_id = $2
        """,
        (payment_id, reseller["reseller_id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    return row



# ---------------------------
# POST /payments (manual input)
# ---------------------------
@router.post("/payments")
async def create_payment(payload: dict, reseller=Depends(auth_reseller_jwt)):
    invoice_id = payload.get("invoice_id")
    amount = payload.get("amount")
    method = payload.get("method")
    provider_txn_id = payload.get("provider_txn_id")
    status = payload.get("status", "success")
    paid_at = payload.get("paid_at") or now_tz()

    invoice = await fetch_one(
        "SELECT * FROM customer_invoices WHERE id=$1 AND reseller_id=$2",
        (invoice_id, reseller["reseller_id"]),
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # insert payment
    await execute(
        """
        INSERT INTO payments (invoice_id, amount, method, provider_txn_id, status, paid_at, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        (invoice_id, amount, method, provider_txn_id, status, now_tz(), now_tz()),
    )

    # update invoice + kirim WA
    if status == "success":
        await execute(
            "UPDATE customer_invoices SET status='paid', paid_at=$1, updated_at=$2 WHERE id=$3",
            (paid_at, now_tz(), invoice_id),
        )
        user = await fetch_one(
            "SELECT u.phone, u.username, u.active_until FROM ppp_users u WHERE u.id=$1",
            (invoice["user_id"],),
        )
        if user:
            await send_wa_message(
                phone=user["phone"],
                text=f"Pembayaran invoice {invoice_id} berhasil. Terima kasih {user['username']}!"
            )

    row = await fetch_one("SELECT * FROM payments WHERE invoice_id=$1 ORDER BY id DESC LIMIT 1", (invoice_id,))
    return row


# ---------------------------
# POST /payments/webhook
# ---------------------------
@router.post("/payments/webhook")
async def payment_webhook(request: Request):
    payload = await request.json()

    provider = payload.get("provider")
    txn_id = payload.get("txn_id")
    invoice_id = payload.get("invoice_id")
    amount = payload.get("amount")
    status = payload.get("status", "pending")
    paid_at = payload.get("paid_at") or now_tz()

    invoice = await fetch_one("SELECT * FROM customer_invoices WHERE id=$1", (invoice_id,))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # cek existing
    existing = await fetch_one("SELECT * FROM payments WHERE provider_txn_id=$1", (txn_id,))
    if existing:
        await execute(
            "UPDATE payments SET status=$1, paid_at=$2 WHERE id=$3",
            (status, paid_at, existing["id"]),
        )
        payment_id = existing["id"]
    else:
        await execute(
            """
            INSERT INTO payments (invoice_id, amount, method, provider_txn_id, status, paid_at, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            (invoice_id, amount, provider, txn_id, status, paid_at, now_tz()),
        )
        row = await fetch_one("SELECT id FROM payments WHERE provider_txn_id=$1", (txn_id,))
        payment_id = row["id"]

    # update invoice + kirim WA
    if status == "success":
        await execute(
            "UPDATE customer_invoices SET status='paid', paid_at=$1, updated_at=$2 WHERE id=$3",
            (paid_at, now_tz(), invoice_id),
        )
        user = await fetch_one(
            "SELECT u.phone, u.username FROM ppp_users u WHERE u.id=$1",
            (invoice["user_id"],),
        )
        if user:
            await send_wa_message(
                phone=user["phone"],
                text=f"Pembayaran invoice {invoice_id} via {provider} berhasil. Terima kasih {user['username']}!"
            )

    return {"message": "Webhook processed", "payment_id": payment_id, "status": status}
