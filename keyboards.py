from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb(rows):
    b = InlineKeyboardBuilder()
    for text, data in rows:
        b.button(text=text, callback_data=data)
    b.adjust(1)
    return b.as_markup()


def main_kb(is_admin=False):
    rows = [
        ('📚 Bo‘limlar', 'user:sections'),
        ('🤖 Bot info', 'user:info'),
    ]
    if is_admin:
        rows.append(('👨‍💼 Admin panel', 'admin:panel'))
    return kb(rows)


def admin_panel_kb():
    return kb([
        ('📚 Bo‘limlar', 'admin:sections'),
        ('📊 Info / statistika', 'admin:stats'),
        ('📩 Arizalar', 'admin:applications'),
        ('👨‍💼 Admin qo‘shish', 'admin:add'),
        ('🤖 Bot info', 'admin:botinfo'),
        ('⬅️ Bosh menyu', 'user:home'),
    ])


def back_admin():
    return kb([('⬅️ Admin panel', 'admin:panel')])
