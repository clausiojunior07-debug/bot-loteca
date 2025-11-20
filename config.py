# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")  # keep as string
GRUPO_ID = os.getenv("GRUPO_ID")
DB_PATH = os.getenv("DB_PATH", "/tmp/palpites.db")
