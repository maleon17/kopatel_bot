import telebot
from telebot import types
from config import BOT_TOKEN
from parser import add_user, user_exists

bot = telebot.TeleBot(BOT_TOKEN)

# FSM
states = {}

WAIT_NICK = "nick"
WAIT_FACTION = "faction"
WAIT_KIT = "kit"
WAIT_CONFIRM = "confirm"

temp = {}


# ───────── keyboards ─────────

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎮 Подать заявку")
    kb.add("📥 Скачать сборку", "ℹ️ Информация")
    return kb


def faction_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔴 Красные", "🔵 Синие")
    return kb


def kit_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        "🪖 Воин",
        "🎯 Снайпер",
        "🛠 Инженер",
        "🚁 Оператор БПЛА",
        "👨‍⚕️ Медик"
    )
    return kb


def confirm_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Да ✅", "Выбрать заново ❌")
    return kb


# ───────── /start ─────────

@bot.message_handler(commands=["start"])
def start(m):
    if user_exists(m.from_user.id):
        bot.send_message(m.chat.id, "Вы уже зарегистрированы.")
        return

    states[m.from_user.id] = WAIT_NICK

    bot.send_message(
        m.chat.id,
        "🛰 Первичный допуск\n======================\nВведите Minecraft ник (3–16 символов, без пробелов)"
    )


# ───────── TEXT HANDLER ─────────

@bot.message_handler(content_types=["text"])
def handler(m):
    uid = m.from_user.id
    text = m.text

    if uid not in states:
        return

    # ─ Nick
    if states[uid] == WAIT_NICK:
        if not text.isalnum() or not (3 <= len(text) <= 16):
            bot.send_message(m.chat.id, "❌ Неверный ник.")
            return

        temp[uid] = {"nick": text}
        states[uid] = WAIT_FACTION

        bot.send_message(m.chat.id, "Выберите фракцию:", reply_markup=faction_kb())
        return

    # ─ Faction
    if states[uid] == WAIT_FACTION:
        if text not in ["🔴 Красные", "🔵 Синие"]:
            return

        temp[uid]["faction"] = text
        states[uid] = WAIT_KIT

        bot.send_message(m.chat.id, "Выберите свой kit:", reply_markup=kit_kb())
        return

    # ─ Kit
    if states[uid] == WAIT_KIT:
        temp[uid]["kit"] = text
        states[uid] = WAIT_CONFIRM

        bot.send_message(
            m.chat.id,
            f'{temp[uid]["nick"]}, Вы выбрали фракцию "{temp[uid]["faction"]}" и kit "{temp[uid]["kit"]}".\nВы уверены?',
            reply_markup=confirm_kb()
        )
        return

    # ─ Confirm
    if states[uid] == WAIT_CONFIRM:

        if text == "Выбрать заново ❌":
            states[uid] = WAIT_NICK
            temp.pop(uid, None)
            bot.send_message(m.chat.id, "Введите Minecraft ник:")
            return

        if text == "Да ✅":

            username = m.from_user.username or "unknown"

            user = {
                "telegram_id": uid,
                "telegram_username": username,
                "minecraft_nick": temp[uid]["nick"],
                "faction": temp[uid]["faction"],
                "kit": temp[uid]["kit"]
            }

            add_user(user)

            # 👇 HERE MC WHITELIST
            # add_to_whitelist(user)

            states.pop(uid)
            temp.pop(uid)

            bot.send_message(m.chat.id, "✅ Заявка принята.")
            return


bot.infinity_polling(skip_pending=True)