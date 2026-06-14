from aiogram.fsm.state import State, StatesGroup

class AuthSG(StatesGroup):
    waiting_password = State()

class TriggerSG(StatesGroup):
    waiting_key = State()
    waiting_response = State()

class TriggerEditSG(StatesGroup):
    waiting_response = State()

class BlacklistSG(StatesGroup):
    waiting_add = State()

class AutobumpSG(StatesGroup):
    waiting_interval = State()

class ReviewReplySG(StatesGroup):
    waiting_text = State()

class TimezoneSG(StatesGroup):
    waiting_value = State()

class WatermarkSG(StatesGroup):
    waiting_text = State()

class ReplySG(StatesGroup):
    waiting_text = State()

class ThanksSG(StatesGroup):
    waiting_text = State()

class QuickReplySG(StatesGroup):
    waiting_text = State()

class PluginUploadSG(StatesGroup):
    waiting_file = State()

class GreetingSG(StatesGroup):
    waiting_text = State()