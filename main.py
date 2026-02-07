import telebot
import sys
import requests
import base64
import json
import time
from telebot import types
from config import BOT_TOKEN, ADMINS, FACTIONS, KITS, MIRROR_GROUP
import parser
from parser import ban_user, unban_user, find_user, is_banned, add_user
from logger import log
from telebot.types import ReplyKeyboardRemove
sys.path.append("/data/data/com.termux/files/home/github_lib")
from github import GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE

bot = telebot.TeleBot(BOT_TOKEN)

sessions = {}


def main_menu(chat):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Начать заново")
    bot.send_message(chat, "Меню:", reply_markup=kb)


@bot.message_handler(commands=["start"])
def start(message):
    
    try:
        sync_github_to_local()
        db = github_load_db()
    except Exception as e:
        print("GitHub load error:", e)
        db = {"users": []}
    
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
        # находим пользователя в базе
        for u in db["users"]:
            if u["telegram_id"] == uid:
                u["banned"] = True
                user = u 
                break
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
        parser.save_db(db)
        github_save_db(db, message=f"Update: user {uid} registered/banned/unbanned")
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
        # находим пользователя в базе
        for u in db["users"]:
            if u["telegram_id"] == uid:
                u["banned"] = False
                user = u 
                break

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
        parser.save_db(db)
        github_save_db(db, message=f"Update: user {uid} registered/banned/unbanned")
    else:
        bot.reply_to(message, "❌ Не удалось разбанить пользователя.")

# ---------------- DEL USER ----------------
@bot.message_handler(commands=["deluser"])
def cmd_deluser(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /deluser <id|username|minecraft>")
        return

    target = args[1].strip()
    user = find_user(target)

    if not user:
        bot.reply_to(message, "❌ Пользователь не найден.")
        return

    uid = user["telegram_id"]
    name = user.get("minecraft") or user.get("username") or str(uid)

    db = parser.load_db()

    # --- удаляем mirror сообщение ---
    if "mirror_msg" in user and MIRROR_GROUP:
        try:
            bot.delete_message(MIRROR_GROUP, user["mirror_msg"])
        except Exception as e:
            print("Mirror delete error:", e)

    # --- удаляем из локальной базы ---
    db["users"] = [u for u in db["users"] if u["telegram_id"] != uid]

    parser.save_db(db)
    github_save_db(db, message=f"DELETE user {uid}")

    bot.send_message(
        message.chat.id,
        f'🗑 Пользователь <a href="tg://user?id={uid}">{name}</a> полностью удалён.',
        parse_mode="HTML"
    )

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
        github_save_db(db, message=f"Update by {message.from_user.username}")

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
        github_save_db(db, message=f"Update by {message.from_user.username}")



        bot.send_message(
            chat_id,
            "✅ Регистрация завершена",
            reply_markup=ReplyKeyboardRemove()
        )
        log(f"NEW USER {uid}")
        sessions.pop(uid)
        return


def github_load_db():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return {"users": []}  # если файла нет
    data = r.json()
    content = base64.b64decode(data['content']).decode()
    return json.loads(content)

def github_save_db(db, message="Update database"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    # ВАЖНО: ensure_ascii=False + utf-8
    content = base64.b64encode(
        json.dumps(db, indent=4, ensure_ascii=False).encode("utf-8")
    ).decode()

    payload = {
        "message": message,
        "content": content
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    return r.status_code in (200, 201)

def sync_github_to_local():
    try:
        db = github_load_db()

        with open("base.jsonc", "w", encoding="utf8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

        print("GitHub → local DB synced")

    except Exception as e:
        print("GitHub sync failed:", e)

print("BOT STARTED")
sync_github_to_local()

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        time.sleep(5)  # просто ждем и переподключаемся