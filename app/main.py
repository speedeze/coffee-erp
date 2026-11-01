from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.config import PROJECT_NAME
from app.database import init_db, SessionLocal
from app.services.seed_data import seed_initial_data

# Routers
from app.routers.auth_router import router as auth_router
from app.routers.dashboard_router import router as dashboard_router
from app.routers.accounting_router import router as accounting_router
from app.routers.inventory_router import router as inventory_router
from app.routers.manufacturing_router import router as manufacturing_router
from app.routers.purchase_router import router as purchase_router
from app.routers.sales_router import router as sales_router
from app.routers.treasury_router import router as treasury_router
from app.routers.users_router import router as users_router

BASE_DIR = Path(__file__).resolve().parent

# Setup Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema & seed initial data on startup
    init_db()
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title=PROJECT_NAME,
    description="Production-Ready Monolith ERP for Coffee Trading and Manufacturing Company",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(accounting_router)
app.include_router(inventory_router)
app.include_router(manufacturing_router)
app.include_router(purchase_router)
app.include_router(sales_router)
app.include_router(treasury_router)
app.include_router(users_router)

if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
