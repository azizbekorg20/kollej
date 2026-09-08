# Telegram guruhlarga qabul bot

## Ishga tushirish
1. Python 3.11+ o‘rnating.
2. `pip install -r requirements.txt`
3. `.env.example` ni `.env` qilib, `BOT_TOKEN` va boshlang‘ich `ADMIN_IDS` ni kiriting.
4. `python main.py`

Bot SQLite (`bot.db`) dan foydalanadi. Baza avtomatik yaratiladi.

## Muhim
- Tasdiqlangan a’zolar soni guruh sig‘imidan oshmasligi uchun tasdiqlash tranzaksiya bilan himoyalangan.
- Bo‘lim/guruh ichida a’zolar yoki arizalar bo‘lsa, tasodifiy o‘chirishga yo‘l qo‘yilmaydi.
- Arizalarda tug‘ilganlik guvohnomasi va 3×4 rasm Telegram `file_id` ko‘rinishida saqlanadi.
- `ADMIN_IDS` ga yozilgan birinchi adminlar baza yaratilganda avtomatik qo‘shiladi.
