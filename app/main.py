from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.db import connect_db, disconnect_db
from app.routers import (
    resellers,
    profiles,
    users,
    invoices,
    payments,
    reports,
    admin,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await connect_db()
    print("✅ Database connected")
    yield
    # shutdown
    await disconnect_db()
    print("🛑 Database disconnected")

app = FastAPI(
    title="Billing ISP API",
    version="1.0.0",
    description="API untuk manajemen reseller, users, invoices, payments, dan reports",
    lifespan=lifespan,
)

# Middleware
origins = [
    "http://127.0.0.1:5000",  # asal frontend kamu
    "http://localhost:5000"
    "https://my.bayarinter.net"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )

# Health Check
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Router Registrasi
app.include_router(resellers.router, prefix="", tags=["Resellers & Auth"])
app.include_router(profiles.router, prefix="", tags=["Profiles"])
app.include_router(users.router, prefix="", tags=["Users"])
app.include_router(invoices.router, prefix="", tags=["Invoices"])
app.include_router(payments.router, prefix="", tags=["Payments"])
app.include_router(reports.router, prefix="", tags=["Reports"])
app.include_router(admin.router, prefix="", tags=["Admin"])
