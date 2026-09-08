import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('8791199481:AAGC1ioPjF8zJCYH7S0MSCRvBgpclcB0b2U', '').strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv('7328068181', '').split(',') if x.strip().isdigit()}
DB_PATH = os.getenv('DB_PATH', 'bot.db')

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN .env faylida kiritilmagan.')
