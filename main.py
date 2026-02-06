import telebot
from telebot import types
from config import BOT_TOKEN, ADMINS, FACTIONS, KITS
import parser
from logger import log
from telebot.types import ReplyKeyboardRemove

bot = telebot.TeleBot(BOT_TOKEN)

sessions = {}


def main_menu(chat):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Начать заново")
    bot.send_message(chat, "Меню:", reply_markup=kb)


@bot.message_handler(commands=["start"])
def start(message):
    sessions[message.from_user.id] = {}
    bot.send_message(message.chat.id,
        "🛰 Первичный допуск\n======================\nВведите Minecraft ник (3–16 символов, без пробелов)")

#-------------ban-------------

@bot.message_handler(commands=["ban"])
def ban(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⛔ Нет прав")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Использование: /ban <id|username|minecraft>")
        return

    target = parts[1].replace("@", "")

    user = parser.find_user(target)

    if not user:
        bot.reply_to(message, "❌ Пользователь не найден")
        return

    parser.ban_user(user)

    bot.reply_to(message, f"🔨 Забанен: {user['minecraft']}")

#-------------unban-------------

@bot.message_handler(commands=["unban"])
def unban(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⛔ Нет прав")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Использование: /unban <id|username|minecraft>")
        return

    target = parts[1].replace("@", "")

    user = parser.find_user(target)

    if not user:
        bot.reply_to(message, "❌ Не найден")
        return

    parser.unban_user(user["telegram_id"])

    bot.reply_to(message, f"✅ Разбанен: {user['minecraft']}")



@bot.message_handler(func=lambda m: True)
def flow(message):
    chat_id = message.chat.id 
    user_id = message.from_user.id
    uid = message.from_user.id

    if parser.is_banned(uid):
        return

    if uid not in sessions:
        return

    s = sessions[uid]

    # ник
    if "nick" not in s:
        nick = message.text.strip()
        if " " in nick or len(nick) < 3 or len(nick) > 16:
            bot.send_message(message.chat.id, "Некорректный ник.")
            return

        s["nick"] = nick

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(FACTIONS[0], FACTIONS[1])

        bot.send_message(message.chat.id, "Выберите фракцию:", reply_markup=kb)
        return

    # фракция
    if "faction" not in s:
        if message.text not in FACTIONS:
            return

        s["faction"] = message.text

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for k in KITS:
            kb.add(k)

        bot.send_message(message.chat.id, "Выберите kit:", reply_markup=kb)
        return

    # kit
    if "kit" not in s:
        if message.text not in KITS:
            return

        s["kit"] = message.text

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("Да ✅", "Выбрать заново ❌")

        bot.send_message(message.chat.id,
            f'{s["nick"]}, Вы выбрали:\nФракция: {s["faction"]}\nKit: {s["kit"]}\n\nПодтвердить?',
            reply_markup=kb)
        return

    # подтверждение
    if message.text == "Выбрать заново ❌":
        sessions.pop(uid)
        start(message)
        return

    if message.text == "Да ✅":
        user = {
            "telegram_id": uid,
            "username": message.from_user.username or "unknown",
            "minecraft": s["nick"],
            "faction": s["faction"],
            "kit": s["kit"],
            "banned": False
        }

        parser.add_user(user)
        bot.send_message(
            chat_id,
            "✅ Регистрация завершена",
            reply_markup=ReplyKeyboardRemove()
        )
        log(f"NEW USER {uid}")
        sessions.pop(uid)
        return


print("BOT STARTED")
bot.infinity_polling()