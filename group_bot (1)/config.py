import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()}
DB_PATH = os.getenv('DB_PATH', 'bot.db')

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN .env faylida kiritilmagan.')
