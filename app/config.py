import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

PROJECT_NAME = os.getenv("PROJECT_NAME", "CoffeeRoast ERP")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/coffee_erp.db")
SECRET_KEY = os.getenv("SECRET_KEY", "coffee-erp-secret-key-production-ready")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
