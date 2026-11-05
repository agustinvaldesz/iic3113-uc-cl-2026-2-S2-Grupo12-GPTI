import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info("Cliente de Supabase inicializado correctamente.")
    except Exception as e:
        logging.error(f"Error al inicializar Supabase: {e}")
else:
    logging.warning("SUPABASE_URL o SUPABASE_KEY no configurados en .env.")