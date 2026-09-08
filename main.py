import asyncio
import logging
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import BOT_TOKEN, ADMIN_IDS, DB_PATH
from db import Database
from states import AdminStates, ApplicationStates
from keyboards import kb, main_kb, admin_panel_kb, back_admin

logging.basicConfig(level=logging.INFO)
db = Database(DB_PATH)
db.seed_admins(ADMIN_IDS)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def user_label(row):
    if row['username']:
        return '@' + row['username']
    name = ' '.join(x for x in [row['first_name'], row['last_name']] if x)
    return name or str(row['user_id'])


def user_label_msg(message):
    return '@' + message.from_user.username if message.from_user.username else (message.from_user.full_name or str(message.from_user.id))


async def notify_admins(text, **kwargs):
    for admin_id in [r['user_id'] for r in _admin_rows()]:
        try:
            await bot.send_message(admin_id, text, **kwargs)
        except Exception as e:
            logging.warning('Admin %s ga yuborilmadi: %s', admin_id, e)


def _admin_rows():
    with db.conn() as c:
        return c.execute('SELECT user_id FROM admins ORDER BY user_id').fetchall()


def require_admin(user_id):
    return db.is_admin(user_id)


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    db.upsert_user(message.from_user)
    text = '<b>Assalomu alaykum!</b>\nKerakli bo‘limni tanlang:'
    await message.answer(text, reply_markup=main_kb(require_admin(message.from_user.id)))


@dp.callback_query(F.data == 'user:home')
async def user_home(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text('Kerakli bo‘limni tanlang:', reply_markup=main_kb(require_admin(call.from_user.id)))
    await call.answer()


@dp.callback_query(F.data == 'user:info')
async def user_info(call: CallbackQuery):
    info = db.get_info()
    await call.message.edit_text(escape(info['text']) if info else 'ℹ️ Bot haqida ma’lumot hali kiritilmagan.', reply_markup=kb([('⬅️ Bosh menyu','user:home')]))
    await call.answer()


@dp.callback_query(F.data == 'user:sections')
async def user_sections(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db.upsert_user(call.from_user)
    if db.user_membership(call.from_user.id):
        m = db.user_membership(call.from_user.id)
        await call.message.edit_text(f'✅ Siz <b>{escape(m["section_name"])}</b> / <b>{escape(m["group_name"])}</b> guruhiga qabul qilingansiz.', reply_markup=kb([('⬅️ Bosh menyu','user:home')]))
        return await call.answer()
    if db.has_pending(call.from_user.id):
        await call.message.edit_text('⏳ Sizning arizangiz hozir ko‘rib chiqilmoqda.', reply_markup=kb([('⬅️ Bosh menyu','user:home')]))
        return await call.answer()
    sections = db.list_sections()
    if not sections:
        await call.message.edit_text('Hozircha bo‘limlar mavjud emas.', reply_markup=kb([('⬅️ Bosh menyu','user:home')]))
        return await call.answer()
    await state.set_state(ApplicationStates.choose_section)
    await call.message.edit_text('📚 <b>Bo‘limni tanlang:</b>', reply_markup=kb([(f'📘 {s["name"]}', f'user:section:{s["id"]}') for s in sections] + [('⬅️ Orqaga','user:home')]))
    await call.answer()


@dp.callback_query(ApplicationStates.choose_section, F.data.startswith('user:section:'))
async def choose_section(call: CallbackQuery, state: FSMContext):
    sid = int(call.data.split(':')[-1])
    if not db.get_section(sid):
        return await call.answer('Bo‘lim topilmadi.', show_alert=True)
    groups = db.list_groups(sid)
    available = [g for g in groups if g['member_count'] < g['capacity']]
    if not available:
        return await call.answer('Bu bo‘limda hozircha bo‘sh joyli guruh yo‘q.', show_alert=True)
    await state.update_data(section_id=sid)
    await state.set_state(ApplicationStates.choose_group)
    buttons = [(f'👥 {g["name"]} — {g["member_count"]}/{g["capacity"]}', f'user:group:{g["id"]}') for g in available]
    buttons.append(('⬅️ Bo‘limlar','user:sections'))
    await call.message.edit_text('👥 <b>Guruhni tanlang:</b>\nFaqat bo‘sh joyi bor guruhlar ko‘rsatilmoqda.', reply_markup=kb(buttons))
    await call.answer()


@dp.callback_query(ApplicationStates.choose_group, F.data.startswith('user:group:'))
async def choose_group(call: CallbackQuery, state: FSMContext):
    gid = int(call.data.split(':')[-1])
    g = db.get_group(gid)
    if not g or g['member_count'] >= g['capacity']:
        await call.answer('Bu guruh to‘lib qoldi. Boshqa guruh tanlang.', show_alert=True)
        return await choose_section(call, state)
    await state.update_data(group_id=gid)
    await state.set_state(ApplicationStates.waiting_birth_certificate)
    await call.message.edit_text('📄 <b>Tug‘ilganlik guvohnomangizni</b> elektron ko‘rinishda rasm yoki PDF sifatida yuboring.')
    await call.answer()


@dp.message(ApplicationStates.waiting_birth_certificate)
async def get_birth(message: Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        birth_type = 'document'
    elif message.photo:
        file_id = message.photo[-1].file_id
        birth_type = 'photo'
    else:
        return await message.answer('Iltimos, tug‘ilganlik guvohnomasini rasm yoki PDF ko‘rinishida yuboring.')
    await state.update_data(birth_id=file_id, birth_type=birth_type)
    await state.set_state(ApplicationStates.waiting_photo)
    await message.answer('🖼️ Endi <b>3×4 rasmingizni</b> elektron ko‘rinishda yuboring.')


@dp.message(ApplicationStates.waiting_photo)
async def get_photo(message: Message, state: FSMContext):
    if not message.photo:
        return await message.answer('Iltimos, 3×4 rasmingizni rasm ko‘rinishida yuboring.')
    data = await state.get_data()
    sid, gid, birth_id, birth_type = data.get('section_id'), data.get('group_id'), data.get('birth_id'), data.get('birth_type')
    photo_id = message.photo[-1].file_id
    ok, result = db.create_application(message.from_user.id, sid, gid, birth_id, birth_type, photo_id)
    if not ok:
        await state.clear()
        return await message.answer('❌ ' + escape(result), reply_markup=main_kb(require_admin(message.from_user.id)))
    g = db.get_group(gid)
    label = user_label_msg(message)
    app_id = result
    text = (f'📩 <b>Yangi ariza #{app_id}</b>\n\n'
            f'👤 Foydalanuvchi: {escape(label)}\n'
            f'🆔 ID: <code>{message.from_user.id}</code>\n'
            f'📚 Bo‘lim: <b>{escape(g["section_name"])}</b>\n'
            f'👥 Guruh: <b>{escape(g["name"])}</b>\n\n'
            f'📄 Tug‘ilganlik guvohnomasi quyida\n'
            f'🖼️ 3×4 rasmi quyida')
    markup = kb([('✅ Tasdiqlash', f'admin:approve:{app_id}'), ('❌ Rad etish', f'admin:reject:{app_id}')])
    for aid in [r['user_id'] for r in _admin_rows()]:
        try:
            sent = await bot.send_message(aid, text, reply_markup=markup)
            db.save_admin_application_message(app_id, aid, sent.message_id)
            if birth_id:
                if birth_type == 'document':
                    await bot.send_document(aid, birth_id)
                else:
                    await bot.send_photo(aid, birth_id)
            await bot.send_photo(aid, photo_id)
        except Exception as e:
            logging.warning('Ariza admin %s ga yuborilmadi: %s', aid, e)
    await state.clear()
    await message.answer('✅ Arizangiz yuborildi. Admin tasdig‘ini kuting.', reply_markup=main_kb(require_admin(message.from_user.id)))


@dp.callback_query(F.data == 'admin:panel')
async def admin_panel(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    await call.message.edit_text('👨‍💼 <b>Admin panel</b>\nKerakli bo‘limni tanlang:', reply_markup=admin_panel_kb())
    await call.answer()


@dp.callback_query(F.data == 'admin:sections')
async def admin_sections(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sections = db.list_sections()
    rows = [('➕ Bo‘lim qo‘shish','admin:section:add'),('➖ Bo‘lim o‘chirish','admin:section:delete')]
    rows += [(f'📘 {s["name"]}', f'admin:section:view:{s["id"]}') for s in sections]
    rows.append(('⬅️ Admin panel','admin:panel'))
    await call.message.edit_text('📚 <b>Bo‘limlar</b>', reply_markup=kb(rows))
    await call.answer()


@dp.callback_query(F.data == 'admin:section:add')
async def section_add(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    await state.set_state(AdminStates.add_section_name)
    await call.message.edit_text('➕ Bo‘lim nomini yuboring:')
    await call.answer()


@dp.message(AdminStates.add_section_name)
async def section_add_name(message: Message, state: FSMContext):
    if not require_admin(message.from_user.id): return
    name = message.text.strip() if message.text else ''
    if not name or len(name) > 100: return await message.answer('Bo‘lim nomi 1–100 belgidan iborat bo‘lsin.')
    if db.add_section(name) is None: return await message.answer('Bu nomdagi bo‘lim allaqachon bor.')
    await state.clear(); await message.answer('✅ Bo‘lim qo‘shildi.', reply_markup=admin_panel_kb())


@dp.callback_query(F.data == 'admin:section:delete')
async def section_delete_start(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sections = db.list_sections()
    if not sections: return await call.answer('Bo‘limlar yo‘q.', show_alert=True)
    await state.set_state(AdminStates.delete_section)
    await call.message.edit_text('O‘chiriladigan bo‘limni tanlang:', reply_markup=kb([(f'🗑️ {s["name"]}', f'admin:section:del:{s["id"]}') for s in sections] + [('⬅️ Orqaga','admin:sections')]))
    await call.answer()


@dp.callback_query(AdminStates.delete_section, F.data.startswith('admin:section:del:'))
async def section_delete(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sid = int(call.data.split(':')[-1])
    ok, err = db.delete_section(sid)
    await state.clear()
    if not ok: return await call.answer(err, show_alert=True)
    await call.answer('Bo‘lim o‘chirildi.')
    await admin_sections(call)


@dp.callback_query(F.data.startswith('admin:section:view:'))
async def section_view(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sid = int(call.data.split(':')[-1]); s = db.get_section(sid)
    if not s: return await call.answer('Topilmadi.', show_alert=True)
    groups = db.list_groups(sid)
    rows = [('➕ Guruh qo‘shish', f'admin:group:add:{sid}'),('➖ Guruh o‘chirish', f'admin:group:delete:{sid}')]
    rows += [(f'👥 {g["name"]} — {g["member_count"]}/{g["capacity"]}', 'noop') for g in groups]
    rows.append(('⬅️ Bo‘limlar','admin:sections'))
    await call.message.edit_text(f'📘 <b>{escape(s["name"])}</b>\nGuruhlar:', reply_markup=kb(rows))
    await call.answer()


@dp.callback_query(F.data.startswith('admin:group:add:'))
async def group_add_start(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sid=int(call.data.split(':')[-1]);
    if not db.get_section(sid): return await call.answer('Bo‘lim topilmadi.', show_alert=True)
    await state.update_data(section_id=sid); await state.set_state(AdminStates.add_group_name)
    await call.message.edit_text('➕ Guruh nomini yuboring:'); await call.answer()


@dp.message(AdminStates.add_group_name)
async def group_add_name(message: Message, state: FSMContext):
    if not require_admin(message.from_user.id): return
    name=message.text.strip() if message.text else ''
    if not name or len(name)>100: return await message.answer('Guruh nomi 1–100 belgidan iborat bo‘lsin.')
    await state.update_data(group_name=name); await state.set_state(AdminStates.add_group_capacity)
    await message.answer('👥 Bu guruhga maksimal nechta odam qabul qilinsin? Masalan: <b>50</b>')


@dp.message(AdminStates.add_group_capacity)
async def group_add_capacity(message: Message, state: FSMContext):
    if not require_admin(message.from_user.id): return
    try: cap=int((message.text or '').strip())
    except ValueError: return await message.answer('Faqat butun son kiriting. Masalan: 50')
    if cap<1 or cap>100000: return await message.answer('Sig‘im 1 dan 100000 gacha bo‘lsin.')
    data=await state.get_data(); gid=db.add_group(data['section_id'],data['group_name'],cap)
    if gid is None: return await message.answer('Bu nomdagi guruh shu bo‘limda allaqachon bor.')
    await state.clear(); await message.answer('✅ Guruh qo‘shildi.', reply_markup=admin_panel_kb())


@dp.callback_query(F.data.startswith('admin:group:delete:'))
async def group_delete_start(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    sid=int(call.data.split(':')[-1]); groups=db.list_groups(sid)
    if not groups: return await call.answer('Bu bo‘limda guruhlar yo‘q.', show_alert=True)
    await state.set_state(AdminStates.delete_group); await state.update_data(section_id=sid)
    await call.message.edit_text('O‘chiriladigan guruhni tanlang:', reply_markup=kb([(f'🗑️ {g["name"]} — {g["member_count"]}/{g["capacity"]}', f'admin:group:del:{g["id"]}') for g in groups] + [('⬅️ Orqaga',f'admin:section:view:{sid}')]))
    await call.answer()


@dp.callback_query(AdminStates.delete_group, F.data.startswith('admin:group:del:'))
async def group_delete(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    gid=int(call.data.split(':')[-1]); data=await state.get_data(); ok,err=db.delete_group(gid); await state.clear()
    if not ok: return await call.answer(err,show_alert=True)
    sid=data['section_id']; s=db.get_section(sid); groups=db.list_groups(sid)
    rows=[('➕ Guruh qo‘shish', f'admin:group:add:{sid}'),('➖ Guruh o‘chirish', f'admin:group:delete:{sid}')]
    rows += [(f'👥 {g["name"]} — {g["member_count"]}/{g["capacity"]}', 'noop') for g in groups]
    rows.append(('⬅️ Bo‘limlar','admin:sections'))
    await call.message.edit_text(f'📘 <b>{escape(s["name"])}</b>\nGuruhlar:', reply_markup=kb(rows))
    await call.answer('Guruh o‘chirildi.')


@dp.callback_query(F.data == 'admin:stats')
async def admin_stats(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    total, sections, groups, pending, rejected = db.stats()
    text=f'📊 <b>Statistika</b>\n\n👤 Jami qabul qilingan: <b>{total}</b>\n📩 Kutilayotgan arizalar: <b>{pending}</b>\n❌ Rad etilgan arizalar: <b>{rejected}</b>\n\n'
    for s in sections: text += f'📘 <b>{escape(s["name"])}</b>: {s["member_count"]} kishi\n'
    text += '\n<b>Guruhlar:</b>\n'
    for g in groups: text += f'• {escape(g["section_name"])} / {escape(g["name"])} — {g["member_count"]}/{g["capacity"]}\n'
    await call.message.edit_text(text, reply_markup=back_admin()); await call.answer()


@dp.callback_query(F.data == 'admin:applications')
async def admin_apps(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    apps=db.list_applications()
    if not apps:
        return await call.message.edit_text('📩 Hozircha arizalar yo‘q.', reply_markup=back_admin())
    rows=[]
    for a in apps:
        status='⏳' if a['status']=='pending' else '❌'
        rows.append((f'{status} #{a["id"]} {user_label(a)} — {a["group_name"]}', f'admin:app:view:{a["id"]}'))
    rows.append(('⬅️ Admin panel','admin:panel'))
    await call.message.edit_text('📩 <b>Arizalar</b>\nTasdiqlanganlar o‘chirildi, rad etilganlar tarixda qoladi.', reply_markup=kb(rows)); await call.answer()


@dp.callback_query(F.data.startswith('admin:app:view:'))
async def app_view(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    aid=int(call.data.split(':')[-1]); a=db.get_application(aid)
    if not a: return await call.answer('Ariza topilmadi.', show_alert=True)
    status='⏳ Kutilmoqda' if a['status']=='pending' else '❌ Rad etilgan'
    text=(f'📩 <b>Ariza #{a["id"]}</b>\n\n👤 {escape(user_label(a))}\n🆔 <code>{a["user_id"]}</code>\n'
          f'📚 {escape(a["section_name"])}\n👥 {escape(a["group_name"])}\n📊 Guruh: {a["member_count"]}/{a["capacity"]}\n📌 Holat: {status}')
    rows=[]
    if a['status']=='pending': rows += [('✅ Tasdiqlash',f'admin:approve:{aid}'),('❌ Rad etish',f'admin:reject:{aid}')]
    rows += [('⬅️ Arizalar','admin:applications')]
    await call.message.edit_text(text,reply_markup=kb(rows))
    try:
        if a['birth_certificate_type'] == 'document':
            await bot.send_document(call.from_user.id,a['birth_certificate_file_id'])
        else:
            await bot.send_photo(call.from_user.id,a['birth_certificate_file_id'])
    except Exception: pass
    try: await bot.send_photo(call.from_user.id,a['photo_file_id'])
    except Exception: pass
    await call.answer()


async def sync_application_admin_messages(app_id, status_text):
    for row in db.get_admin_application_messages(app_id):
        try:
            await bot.edit_message_text(
                chat_id=row['admin_id'],
                message_id=row['message_id'],
                text=status_text,
                reply_markup=None,
            )
        except Exception as e:
            logging.warning('Admin application message sync failed: %s', e)


@dp.callback_query(F.data.startswith('admin:approve:'))
async def approve(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    aid=int(call.data.split(':')[-1]); ok,err,a=db.approve_application(aid)
    if not ok: return await call.answer(err,show_alert=True)
    g = db.get_group(a['group_id'])
    try: await bot.send_message(a['user_id'], f'🎉 Arizangiz tasdiqlandi!\n\n📚 {escape(g["section_name"])}\n👥 {escape(g["name"])}')
    except Exception: pass
    await sync_application_admin_messages(aid, f'✅ <b>Ariza #{aid} tasdiqlandi</b>\n👤 {escape(user_label(a))}\n📚 {escape(g["section_name"])}\n👥 {escape(g["name"])}')
    await call.answer('Ariza tasdiqlandi.')
    await admin_apps(call)


@dp.callback_query(F.data.startswith('admin:reject:'))
async def reject(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    aid=int(call.data.split(':')[-1]); ok,err,a=db.reject_application(aid)
    if not ok: return await call.answer(err,show_alert=True)
    g = db.get_group(a['group_id'])
    try: await bot.send_message(a['user_id'], '❌ Arizangiz rad etildi. Istasangiz, boshqa bo‘lim/guruhni tanlab qayta ariza yuborishingiz mumkin.')
    except Exception: pass
    await sync_application_admin_messages(aid, f'❌ <b>Ariza #{aid} rad etildi</b>\n👤 {escape(user_label(a))}\n📚 {escape(g["section_name"])}\n👥 {escape(g["name"])}')
    await call.answer('Ariza rad etildi.')
    await admin_apps(call)


@dp.callback_query(F.data == 'admin:add')
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    await state.set_state(AdminStates.add_admin_id); await call.message.edit_text('👨‍💼 Yangi adminning Telegram ID raqamini yuboring:'); await call.answer()


@dp.message(AdminStates.add_admin_id)
async def add_admin_id(message: Message, state: FSMContext):
    if not require_admin(message.from_user.id): return
    try: uid=int((message.text or '').strip())
    except ValueError: return await message.answer('Telegram ID faqat raqam bo‘lishi kerak.')
    db.add_admin(uid); await state.clear(); await message.answer(f'✅ <code>{uid}</code> adminlar ro‘yxatiga qo‘shildi.', reply_markup=admin_panel_kb())
    try: await bot.send_message(uid, '👨‍💼 Siz botga admin qilib tayinlandingiz. /start bosing.')
    except Exception: pass


@dp.callback_query(F.data == 'admin:botinfo')
async def admin_botinfo(call: CallbackQuery):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.', show_alert=True)
    info=db.get_info(); current=escape(info['text']) if info else 'Hali info kiritilmagan.'
    await call.message.edit_text(f'🤖 <b>Bot info</b>\n\n{current}', reply_markup=kb([('✏️ Info qo‘shish / almashtirish','admin:botinfo:set'),('⬅️ Admin panel','admin:panel')]))
    await call.answer()


@dp.callback_query(F.data == 'admin:botinfo:set')
async def botinfo_set_start(call: CallbackQuery,state:FSMContext):
    if not require_admin(call.from_user.id): return await call.answer('Ruxsat yo‘q.',show_alert=True)
    await state.set_state(AdminStates.set_bot_info); await call.message.edit_text('🤖 Yangi bot info matnini yuboring. Eski info almashtiriladi.'); await call.answer()


@dp.message(AdminStates.set_bot_info)
async def botinfo_set(message:Message,state:FSMContext):
    if not require_admin(message.from_user.id): return
    text=message.text.strip() if message.text else ''
    if not text: return await message.answer('Info matni bo‘sh bo‘lmasin.')
    if len(text)>4000: return await message.answer('Info 4000 belgidan oshmasin.')
    db.set_info(text); await state.clear(); await message.answer('✅ Bot info saqlandi.',reply_markup=admin_panel_kb())


@dp.callback_query(F.data == 'noop')
async def noop(call:CallbackQuery): await call.answer()


async def main():
    logging.info('Bot ishga tushdi')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
