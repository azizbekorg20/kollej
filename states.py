from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    add_section_name = State()
    delete_section = State()
    add_group_name = State()
    add_group_capacity = State()
    delete_group = State()
    add_admin_id = State()
    set_bot_info = State()

class ApplicationStates(StatesGroup):
    choose_section = State()
    choose_group = State()
    waiting_birth_certificate = State()
    waiting_photo = State()
