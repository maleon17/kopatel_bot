import telebot
import sys
from telebot import types
from config import BOT_TOKEN, ADMINS, FACTIONS, KITS, MIRROR_GROUP
import parser
from parser import ban_user, unban_user, find_user, is_banned, add_user
from logger import log
from telebot.types import ReplyKeyboardRemove
sys.path.append("/data/data/com.termux/files/home/github_lib")
from github import GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE_PATH

bot = telebot.TeleBot(BOT_TOKEN)

sessions = {}


def main_menu(chat):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Начать заново")
    bot.send_message(chat, "Меню:", reply_markup=kb)


@bot.message_handler(commands=["start"])
def start(message):

    # игнорируем группы
    if message.chat.type != "private":
        return

    uid = message.from_user.id
    existing = find_user(uid)

    if existing:
        bot.send_message(
            message.chat.id,
            f"Пользователь уже зарегистрирован ❌\n"
            f"{existing['minecraft']}, вы выбрали:\nФракция: {existing['faction']}\nKit: {existing['kit']}",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    sessions[uid] = {}
    bot.send_message(
        message.chat.id,
        "🛰 Первичный допуск\n======================\nВведите Minecraft ник (3–16 символов, без пробелов)",
        reply_markup=ReplyKeyboardRemove()
    )


# ---------------- BAN ----------------
@bot.message_handler(commands=["ban"])
def cmd_ban(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /ban <id|username|minecraft>")
        return

    target = args[1].strip()
    user = find_user(target)
    if not user:
        bot.reply_to(message, f"⚠ Пользователь '{target}' не найден.")
        return

    if ban_user(target):
        uid = user["telegram_id"]
        name = user.get("minecraft") or user.get("username") or str(uid)

        # --- обновляем сообщение в зеркале ---
        db = parser.load_db()
        if "mirror_msg" in user and MIRROR_GROUP:
            try:
                text = (
                    f"🆔 {uid}\n"
                    f"🎮 {user.get('minecraft')}\n"
                    f"👤 @{user.get('username')}\n"
                    f"🏳 {user.get('faction')}\n"
                    f"🧰 {user.get('kit')}\n"
                    f"🚫 banned: true"
                )
                bot.edit_message_text(
                    chat_id=MIRROR_GROUP,
                    message_id=user["mirror_msg"],
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                print("Mirror update error:", e)

        bot.send_message(
            message.chat.id,
            f'✅ Пользователь <a href="tg://user?id={uid}">{name}</a> забанен.',
            parse_mode="HTML"
        )
    else:
        bot.reply_to(message, "❌ Не удалось забанить пользователя.")


# ---------------- UNBAN ----------------
@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /unban <id|username|minecraft>")
        return

    target = args[1].strip()
    user = find_user(target)
    if not user:
        bot.reply_to(message, f"⚠ Пользователь '{target}' не найден.")
        return

    if unban_user(target):
        uid = user["telegram_id"]
        name = user.get("minecraft") or user.get("username") or str(uid)

        # --- обновляем сообщение в зеркале ---
        db = parser.load_db()
        if "mirror_msg" in user and MIRROR_GROUP:
            try:
                text = (
                    f"🆔 {uid}\n"
                    f"🎮 {user.get('minecraft')}\n"
                    f"👤 @{user.get('username')}\n"
                    f"🏳 {user.get('faction')}\n"
                    f"🧰 {user.get('kit')}\n"
                    f"🚫 banned: false"
                )
                bot.edit_message_text(
                    chat_id=MIRROR_GROUP,
                    message_id=user["mirror_msg"],
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                print("Mirror update error:", e)

        bot.send_message(
            message.chat.id,
            f'✅ Пользователь <a href="tg://user?id={uid}">{name}</a> разбанен.',
            parse_mode="HTML"
        )
    else:
        bot.reply_to(message, "❌ Не удалось разбанить пользователя.")


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

        # Загружаем базу
        db = parser.load_db()
        
        # Проверяем, есть ли уже пользователь
        exists = False
        for i, u in enumerate(db["users"]):
            if u["telegram_id"] == uid:
                db["users"][i] = user
                exists = True
                break

        # Если нового пользователя — добавляем
        if not exists:
            db["users"].append(user)

        # Сохраняем базу
        parser.save_db(db)

        text = (
            f"🆔 {uid}\n"
            f"🎮 {s['nick']}\n"
            f"👤 @{message.from_user.username}\n"
            f"🏳 {s['faction']}\n"
            f"🧰 {s['kit']}\n"
            f"🚫 banned: false"
        )

        msg = bot.send_message(MIRROR_GROUP, text)

        db = parser.load_db()

        for u in db["users"]:
            if u["telegram_id"] == uid:
                u["mirror_msg"] = msg.message_id

        parser.save_db(db)



        bot.send_message(
            chat_id,
            "✅ Регистрация завершена",
            reply_markup=ReplyKeyboardRemove()
        )
        log(f"NEW USER {uid}")
        sessions.pop(uid)
        return

def mirror_load_db():
    """Считываем все сообщения из группы и создаем базу восстановления"""
    db = {"users": []}

    try:
        for msg in bot.get_chat(MIRROR_GROUP).get_history(limit=1000):  # или нужный лимит
            # проверяем формат сообщения
            if not msg.text:
                continue
            lines = msg.text.splitlines()
            if len(lines) < 6:
                continue

            try:
                uid = int(lines[0].split("🆔")[1].strip())
                minecraft = lines[1].split("🎮")[1].strip()
                username = lines[2].split("👤")[1].strip().replace("@", "")
                faction = lines[3].split("🏳")[1].strip()
                kit = lines[4].split("🧰")[1].strip()
                banned = lines[5].split("🚫 banned:")[1].strip().lower() == "true"
            except:
                continue

            db["users"].append({
                "telegram_id": uid,
                "minecraft": minecraft,
                "username": username,
                "faction": faction,
                "kit": kit,
                "banned": banned,
                "mirror_msg": msg.message_id
            })
    except Exception as e:
        print("Mirror load error:", e)

    parser.save_db(db)
    print("✅ База восстановлена из зеркала")

mirror_load_db()
print("BOT STARTED")
bot.infinity_polling()