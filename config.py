# config.py

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = os.getenv("ADMIN_ID")
GRUPO_ID    = os.getenv("GRUPO_ID")

# Novo — usado pela v6.2 para exportação
EXPORTS_DIR = os.getenv("EXPORTS_DIR", "exports")

# Caminho do banco de dados
DB_PATH = os.getenv("DB_PATH", "palpites_v2.db")


