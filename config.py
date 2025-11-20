# config.py

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = os.getenv("ADMIN_ID")
GRUPO_ID    = os.getenv("GRUPO_ID")
EXPORTS_DIR = os.getenv("EXPORTS_DIR", "exports")

# IMPORTANTE: No Render, use a variável de ambiente diretamente
DB_PATH = os.getenv("DB_PATH", "palpites.db")
