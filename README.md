# ISP Billing System (FastAPI + Worker)

Sistem billing untuk integrasi **Mikrotik + FreeRADIUS**, dibangun dengan **FastAPI** dan **PostgreSQL**, dilengkapi **scheduler worker** untuk otomatisasi invoice dan notifikasi via WhatsApp.

---

## 📂 Struktur Project
```
.
│ .env # Konfigurasi environment (ignored by git)
│ example.env # Template konfigurasi environment
│ docker-compose.yml # Compose untuk production
│ docker-compose.override.yml # Compose override untuk development (hot reload)
│ Dockerfile # Build image FastAPI & Worker
│ requirements.txt # Python dependencies
│
└───app
│ config.py
│ db.py
│ deps.py
│ main.py
│ utils.py
│
├───routers # Semua endpoint API
│ admin.py
│ invoices.py
│ payments.py
│ profiles.py
│ reports.py
│ resellers.py
│ users.py
│ init.py
│
└───worker # Worker job scheduler
run.py
scheduler.py
``` 

---

## 🚀 Cara Setup

### 1. Clone Repo
```
git clone https://github.com/username/isp-billing.git
cd isp-billing
```
### 2. Konfigurasi Environment
Copy example.env menjadi .env lalu edit sesuai kebutuhan:

```
cp example.env .env
nano .env
```

Isi parameter utama:
```
DATABASE_URL → koneksi PostgreSQL
JWT_SECRET → secret key JWT
WA_GATEWAY_URL + WA_TOKEN → integrasi WhatsApp gateway
```
### 3. Build dan Jalankan dengan Docker Compose

Production Mode
```
docker compose up -d --build
```

Development Mode (auto reload)
```
docker compose up
```
### 4. Akses API
API berjalan di: http://localhost:8000

Dokumentasi OpenAPI: http://localhost:8000/docs

🛠 Worker Jobs
Worker otomatis menjalankan task berikut:
```
Generate Customer Invoices → H-3 dari active_until
Reminder Unpaid → 5 hari sebelum akhir bulan active_until
Suspend User → tiap tanggal 1, suspend user yang masih unpaid
Generate Reseller Invoices → tiap tanggal 1, tagihan reseller bulan sebelumnya
```
📦 Dependensi Utama
```
FastAPI
Uvicorn
asyncpg
psycopg2
python-jose
passlib
APScheduler
httpx
```
📌 Notes

Postgres & FreeRADIUS di-manage eksternal (tidak dijalankan lewat Docker Compose ini).

Worker & API berjalan di network cloudflare_net → pastikan network sudah dibuat:
```
docker network create cloudflare_net
```
🧑‍💻 Development

Semua kode Python ada di folder app/
Endpoint ada di app/routers/
Worker job ada di app/worker/

⚡ License
MIT 

--- 

## 🔄 Alur Invoice & Payment

```mermaid
flowchart TD
    A[User Active Until] -->|H-3| B[Generate Customer Invoice]
    B --> C[WA Notifikasi Tagihan]

    C --> D[Customer Membayar]
    D -->|via /invoices/{id}/pay| E[Update Invoice Paid + Tambah Payment]
    E --> F[WA Konfirmasi Pembayaran]

    C -->|Tidak Bayar| G[Reminder Unpaid (5 hari sebelum akhir bulan)]
    G -->|Masih Unpaid| H[Suspend User (Tanggal 1 bulan berikutnya)]
    H --> I[WA Notifikasi Suspend]

    J[Setiap tanggal 1] --> K[Generate Reseller Invoice]
    K --> L[WA Notifikasi Tagihan Reseller]
    L --> M[Reseller Membayar]
    M --> N[Update Reseller Invoice Paid + WA Konfirmasi]
```