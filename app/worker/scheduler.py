from datetime import date, datetime, timedelta
from app.db import fetch_all, execute
from app.utils import send_wa_message

# ========== CUSTOMER INVOICES ==========
async def job_generate_customer_invoices():
    today = date.today()
    print(f"[{datetime.now()}] Running job_generate_customer_invoices...")

    # Cari user dengan active_until = today + 3 hari
    users = await fetch_all(
        """
        SELECT u.*, p.price, p.name as profile_name
        FROM ppp_users u
        JOIN ppp_profiles p ON p.id = u.profile_id
        WHERE u.active_until = $1
          AND u.deleted_at IS NULL
          AND u.is_active = true
        """,
        (today + timedelta(days=3),),
    )

    for u in users:
        # Cek apakah sudah ada invoice untuk periode ini
        existing = await fetch_all(
            """
            SELECT 1 FROM customer_invoices
            WHERE user_id=$1 AND period_start=$2 AND period_end=$3
            """,
            (u["id"], u["active_until"], u["active_until"] + timedelta(days=30)),  # approx satu bulan
        )
        if existing:
            continue

        inv = await execute(
            """
            INSERT INTO customer_invoices (reseller_id, user_id, profile_id, period_start, period_end, amount, status, meta)
            VALUES ($1,$2,$3,$4,$5,$6,'unpaid', jsonb_build_object('auto_generated', true))
            RETURNING id
            """,
            (
                u["reseller_id"], u["id"], u["profile_id"],
                u["active_until"], u["active_until"] + timedelta(days=30),
                u["price"],
            ),
        )
        print(f"Generated invoice {inv['id']} for user {u['username']}")

        await send_wa_message(
            u["phone"],
            f"Halo {u['username']}, tagihan baru untuk paket {u['profile_name']} "
            f"senilai {u['price']} jatuh tempo {u['active_until']}. Harap segera dibayar."
        )


# ========== REMINDER UNPAID ==========
async def job_remind_unpaid_invoices():
    today = date.today()
    print(f"[{datetime.now()}] Running job_remind_unpaid_invoices...")

    invoices = await fetch_all(
        """
        SELECT ci.*, u.username, u.phone, u.active_until
        FROM customer_invoices ci
        JOIN ppp_users u ON u.id=ci.user_id
        WHERE ci.status='unpaid'
    """,
    )

    for inv in invoices:
        # hitung akhir bulan active_until
        au = inv["active_until"]
        month_end = (au.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        remind_date = month_end - timedelta(days=5)

        if remind_date == today:
            print(f"Reminder unpaid for invoice {inv['id']} (user {inv['username']})")
            await send_wa_message(
                inv["phone"],
                f"Halo {inv['username']}, tagihan Anda untuk periode {inv['period_start']} - {inv['period_end']} "
                f"masih belum dibayar. Mohon segera lunasi sebelum {month_end}."
            )


# ========== SUSPEND USERS ==========
async def job_suspend_overdue_users():
    today = date.today()
    print(f"[{datetime.now()}] Running job_suspend_overdue_users...")

    # Cari invoice unpaid dengan active_until bulan lalu
    invoices = await fetch_all(
        """
        SELECT ci.*, u.username, u.phone
        FROM customer_invoices ci
        JOIN ppp_users u ON u.id=ci.user_id
        WHERE ci.status='unpaid'
          AND ci.period_end < date_trunc('month', $1)::date
        """,
        (today,),
    )

    for inv in invoices:
        await execute("UPDATE ppp_users SET status='suspended' WHERE id=$1", (inv["user_id"],))
        print(f"Suspended user {inv['username']} (invoice {inv['id']})")

        await send_wa_message(
            inv["phone"],
            f"Halo {inv['username']}, layanan Anda disuspend per 1 {today.strftime('%B %Y')} "
            f"karena tagihan belum dibayar."
        )


# ========== GENERATE INVOICES FOR RESELLERS ==========
async def job_generate_reseller_invoices():
    today = date.today()
    print(f"[{datetime.now()}] Running job_generate_reseller_invoices...")

    # Hitung periode bulan lalu
    period_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    period_end = today.replace(day=1) - timedelta(days=1)

    resellers = await fetch_all("SELECT * FROM resellers")

    for r in resellers:
        users_count = await fetch_all(
            """
            SELECT COUNT(*)::int as cnt
            FROM ppp_users
            WHERE reseller_id=$1 AND status='active'
              AND (active_until BETWEEN $2 AND $3)
            """,
            (r["id"], period_start, period_end),
        )
        count = users_count[0]["cnt"]

        subtotal = count * r["price_per_user"]
        discount = 0  # placeholder
        tax = 0
        total = subtotal - discount + tax

        # insert invoice jika belum ada
        inv = await execute(
            """
            INSERT INTO invoices (reseller_id, period_start, period_end, users_count, unit_price, subtotal, discount, tax, total, currency, status, meta)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'unpaid', jsonb_build_object('reseller_name',$11))
            ON CONFLICT (reseller_id, period_start, period_end) DO NOTHING
            RETURNING id
            """,
            (
                r["id"], period_start, period_end, count,
                r["price_per_user"], subtotal, discount, tax, total, r["currency"], r["name"],
            ),
        )
        if inv:
            print(f"Generated reseller invoice {inv['id']} for {r['name']}")
            await send_wa_message(
                r["phone"],
                f"Halo {r['name']}, invoice bulan {period_start.strftime('%B %Y')} "
                f"dengan total {total} sudah dibuat. Mohon dibayar sebelum tanggal 20."
            )
