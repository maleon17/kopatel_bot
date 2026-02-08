import telebot
import sys
import requests
import base64
import json
import time
import logging 
import queue
import threading
import multiprocessing 
import string
import random
from datetime import datetime, timedelta
from mcrcon import MCRcon
from telebot import types
import parser
from parser import ban_user, unban_user, find_user, is_banned, add_user
from logger import log
from telebot.types import ReplyKeyboardRemove
from config import BOT_TOKEN, ADMINS, FACTIONS, KITS, MIRROR_GROUP, RCON_HOST, RCON_PORT, RCON_PASSWORD

# Flask для API
from flask import Flask, request, jsonify

sys.path.append("/data/data/com.termux/files/home/github_lib")
from github import GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE


logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("telebot").setLevel(logging.CRITICAL)
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

sessions = {}

# ----------------- FLASK API -----------------

@app.route('/check_code', methods=['GET'])
def check_code():
    """API для проверки кода подтверждения модом"""
    nick = request.args.get('nick')
    code = request.args.get('code')
    
    if not nick or not code:
        return jsonify({"valid": False, "error": "Missing parameters"})
    
    # Ищем пользователя по minecraft нику
    user = find_user(nick)
    
    if not user:
        return jsonify({"valid": False, "error": "User not found"})
    
    # Проверяем код
    if not user.get("verification_code"):
        return jsonify({"valid": False, "error": "No code generated"})
    
    if user["verification_code"].upper() != code.upper():
        return jsonify({"valid": False, "error": "Invalid code"})
    
    # Проверяем срок действия
    if "code_expires" in user:
        expires = datetime.fromisoformat(user["code_expires"])
        if datetime.now() > expires:
            return jsonify({"valid": False, "error": "Code expired"})
    
    # Помечаем код как использованный и обновляем время
    db = parser.load_db()
    for u in db["users"]:
        if u["telegram_id"] == user["telegram_id"]:
            u["code_used"] = True
            u["last_verified"] = datetime.now().isoformat()
            break
    
    parser.save_db(db)
    
    # Уведомляем пользователя в Telegram
    try:
        bot.send_message(
            user["telegram_id"],
            f"✅ Вход на сервер подтверждён!\n"
            f"🎮 Ник: {nick}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
        )
    except:
        pass
    
    return jsonify({"valid": True, "username": user.get("username"), "telegram_id": user["telegram_id"]})

@app.route('/player_join', methods=['POST'])
def player_join():
    """API для уведомлений о входе игрока (опционально)"""
    data = request.get_json()
    nick = data.get('nick')
    
    user = find_user(nick)
    if user:
        try:
            bot.send_message(
                user["telegram_id"],
                f"🔔 Попытка входа на сервер\n"
                f"🎮 Ник: {nick}\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"Если это не вы, срочно смените код командой /getcode"
            )
        except:
            pass
    
    return jsonify({"status": "ok"})

def run_flask():
    """Запуск Flask сервера в отдельном потоке"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Запускаем Flask в отдельном потоке
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
print("✅ Flask API started on http://0.0.0.0:5000")

# ----------------- RCON PROCESS -------------------

# Очередь команд для процесса
rcon_queue = multiprocessing.Queue()

def rcon_process_worker(queue, host, port, password):
    """Процесс для выполнения команд RCON"""
    while True:
        cmd = queue.get()
        if cmd is None:
            break
        try:
            action = cmd[0]
            
            if action == "custom":
                command = cmd[1]
                with MCRcon(host, password, port=port) as mcr:
                    resp = mcr.command(command)
                    print(f"RCON: {command} -> {resp}")
                continue
            
            nick = cmd[1]
            if not nick:
                continue
            with MCRcon(host, password, port=port) as mcr:
                if action == "ban":
                    resp = mcr.command(f"ban {nick}")
                    print(f"RCON: ban {nick} -> {resp}")
                elif action == "unban":
                    resp = mcr.command(f"pardon {nick}")
                    print(f"RCON: unban {nick} -> {resp}")
                elif action == "del":
                    resp = mcr.command(f"whitelist remove {nick}")
                    print(f"RCON: del {nick} -> {resp}")
                elif action == "whitelist":
                    resp = mcr.command(f"whitelist add {nick}")
                    print(f"RCON: whitelist add {nick} -> {resp}")
                elif action == "op":
                    resp = mcr.command(f"op {nick}")
                    print(f"RCON: op {nick} -> {resp}")
                elif action == "deop":
                    resp = mcr.command(f"deop {nick}")
                    print(f"RCON: deop {nick} -> {resp}")
        except Exception as e:
            print("RCON ERROR:", e)

rcon_process = multiprocessing.Process(
    target=rcon_process_worker, 
    args=(rcon_queue, RCON_HOST, RCON_PORT, RCON_PASSWORD),
    daemon=True
)
rcon_process.start()

def rcon_ban(nick):
    rcon_queue.put(("ban", nick))

def rcon_unban(nick):
    rcon_queue.put(("unban", nick))

def rcon_del_user(nick):
    rcon_queue.put(("del", nick))

def rcon_whitelist_add(nick):
    rcon_queue.put(("whitelist", nick))

def rcon_op(nick):
    rcon_queue.put(("op", nick))

def rcon_deop(nick):
    rcon_queue.put(("deop", nick))

def rcon_custom_command(command):
    rcon_queue.put(("custom", command))

def generate_code():
    """Генерирует случайный 6-значный код"""
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace('O', '').replace('I', '').replace('0', '').replace('1', '')
    return ''.join(random.choice(chars) for _ in range(6))

@bot.message_handler(commands=["getcode", "code"])
def cmd_getcode(message):
    if message.chat.type != "private":
        return
    
    uid = message.from_user.id
    user = find_user(uid)
    
    if not user:
        bot.reply_to(message, "❌ Вы не зарегистрированы. Используйте /start")
        return
    
    code = generate_code()
    expires = datetime.now() + timedelta(hours=24)
    
    db = parser.load_db()
    for u in db["users"]:
        if u["telegram_id"] == uid:
            u["verification_code"] = code
            u["code_expires"] = expires.isoformat()
            u["code_used"] = False
            break
    
    parser.save_db(db)
    github_save_db(db, message=f"Generate code for {uid}")
    
    bot.send_message(
        message.chat.id,
        f"🔐 <b>Код подтверждения для сервера</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"⏰ Действителен: 24 часа\n"
        f"📝 Введите в Minecraft:\n"
        f"<code>/verify {code}</code>",
        parse_mode="HTML"
    )
    
    log(f"Code generated for {uid}: {code}")

@bot.message_handler(commands=["start"])
def start(message):
    try:
        sync_github_to_local()
        db = github_load_db()
    except Exception as e:
        print("GitHub load error:", e)
        db = {"users": []}

    if message.chat.type != "private":
        return

    uid = message.from_user.id
    existing = find_user(uid)

    if existing:
        bot.send_message(
            message.chat.id,
            f"Пользователь уже зарегистрирован ❌\n"
            f"{existing['minecraft']}, вы выбрали:\nФракция: {existing['faction']}\nKit: {existing['kit']}\n\n"
            f"💡 Используйте /getcode для получения кода входа на сервер",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    sessions[uid] = {}
    bot.send_message(
        message.chat.id,
        "🛰 Первичный допуск\n======================\nВведите Minecraft ник (3–16 символов, без пробелов)",
        reply_markup=ReplyKeyboardRemove()
    )

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
        if user.get("minecraft"):
            rcon_ban(user["minecraft"]) 

        db = parser.load_db()
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
                    f"👤 {user.get('username')}\n"
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
        github_save_db(db, message=f"Ban user {uid}")
    else:
        bot.reply_to(message, "❌ Не удалось забанить пользователя.")

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
        if user.get("minecraft"):
            rcon_unban(user["minecraft"])

        db = parser.load_db()
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
                    f"👤 {user.get('username')}\n"
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
        github_save_db(db, message=f"Unban user {uid}")
    else:
        bot.reply_to(message, "❌ Не удалось разбанить пользователя.")

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

    if "mirror_msg" in user and MIRROR_GROUP:
        try:
            bot.delete_message(MIRROR_GROUP, user["mirror_msg"])
        except Exception as e:
            print("Mirror delete error:", e)

    db["users"] = [u for u in db["users"] if u["telegram_id"] != uid]

    parser.save_db(db)
    github_save_db(db, message=f"Delete user {uid}")

    if user.get("minecraft"):
        rcon_del_user(user["minecraft"])

    bot.send_message(
        message.chat.id,
        f'🗑 Пользователь <a href="tg://user?id={uid}">{name}</a> полностью удалён.',
        parse_mode="HTML"
    )

@bot.message_handler(commands=["syncwhitelist"])
def cmd_sync_whitelist(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    bot.send_message(message.chat.id, "⏳ Синхронизация whitelist...")

    db = parser.load_db()
    
    added_count = 0
    error_count = 0
    
    for user in db["users"]:
        if user.get("banned", False):
            continue
        
        if not user.get("minecraft"):
            continue
        
        try:
            rcon_whitelist_add(user["minecraft"])
            added_count += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"Error adding {user['minecraft']} to whitelist: {e}")
            error_count += 1
    
    bot.send_message(
        message.chat.id,
        f"✅ Синхронизация завершена!\n\n"
        f"📊 Статистика:\n"
        f"• Добавлено в whitelist: {added_count}\n"
        f"• Ошибок: {error_count}\n"
        f"• Всего в базе: {len(db['users'])}\n"
        f"• Забанено: {sum(1 for u in db['users'] if u.get('banned', False))}"
    )

@bot.message_handler(commands=["op"])
def cmd_op(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /op <id|username|minecraft>")
        return

    target = args[1].strip()
    user = find_user(target)
    
    if not user:
        bot.reply_to(message, f"⚠ Пользователь '{target}' не найден.")
        return

    if not user.get("minecraft"):
        bot.reply_to(message, "❌ У пользователя нет Minecraft ника.")
        return

    uid = user["telegram_id"]
    minecraft_nick = user["minecraft"]
    name = user.get("username") or str(uid)

    rcon_op(minecraft_nick)

    bot.send_message(
        message.chat.id,
        f'👑 Пользователю <a href="tg://user?id={uid}">{name}</a> ({minecraft_nick}) выданы OP-права.',
        parse_mode="HTML"
    )
    log(f"OP granted to {uid} ({minecraft_nick})")

@bot.message_handler(commands=["deop"])
def cmd_deop(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /deop <id|username|minecraft>")
        return

    target = args[1].strip()
    user = find_user(target)
    
    if not user:
        bot.reply_to(message, f"⚠ Пользователь '{target}' не найден.")
        return

    if not user.get("minecraft"):
        bot.reply_to(message, "❌ У пользователя нет Minecraft ника.")
        return

    uid = user["telegram_id"]
    minecraft_nick = user["minecraft"]
    name = user.get("username") or str(uid)

    rcon_deop(minecraft_nick)

    bot.send_message(
        message.chat.id,
        f'🚫 У пользователя <a href="tg://user?id={uid}">{name}</a> ({minecraft_nick}) забраны OP-права.',
        parse_mode="HTML"
    )
    log(f"OP removed from {uid} ({minecraft_nick})")

@bot.message_handler(commands=["command", "cmd"])
def cmd_custom_command(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Использование: /command <minecraft команда>\n\n"
                              "Примеры:\n"
                              "/command tp slastika UlanaFo\n"
                              "/command tp b_b_e_e_a_a_u_u_t_t_y_y nikd134\n"
                              "/command give 2091726116 diamond 64\n"
                              "/command gamemode creative maleon17")
        return

    command = args[1].strip()
    original_command = command
    
    words = command.split()
    db = parser.load_db()
    
    converted_words = []
    conversions = []
    
    for word in words:
        user = find_user(word)
        if user and user.get("minecraft"):
            converted_words.append(user["minecraft"])
            conversions.append(f"{word} → {user['minecraft']}")
        else:
            converted_words.append(word)
    
    final_command = " ".join(converted_words)
    
    rcon_custom_command(final_command)
    
    if conversions:
        conversion_text = "\n".join([f"• {c}" for c in conversions])
        bot.send_message(
            message.chat.id,
            f"✅ Команда отправлена на сервер!\n\n"
            f"📝 Оригинал:\n<code>{original_command}</code>\n\n"
            f"🔄 Конвертировано:\n{conversion_text}\n\n"
            f"📤 Итоговая команда:\n<code>{final_command}</code>",
            parse_mode="HTML"
        )
    else:
        bot.send_message(
            message.chat.id,
            f"✅ Команда отправлена на сервер!\n\n"
            f"📤 Команда:\n<code>{final_command}</code>",
            parse_mode="HTML"
        )
    
    log(f"Custom command: {final_command} (by {message.from_user.id})")

@bot.message_handler(func=lambda m: True)
def flow(message):
    chat_id = message.chat.id 
    user_id = message.from_user.id
    uid = message.from_user.id

    if message.chat.type != "private":
        return

    if parser.is_banned(uid):
        return

    if uid not in sessions:
        return

    s = sessions[uid]

    if "nick" not in s:
        nick = message.text.strip()
        if " " in nick or len(nick) < 3 or len(nick) > 16:
            bot.send_message(message.chat.id, "❌ Некорректный ник. Введите ник от 3 до 16 символов без пробелов.")
            return

        s["nick"] = nick

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(FACTIONS[0], FACTIONS[1])

        bot.send_message(message.chat.id, "Выберите фракцию:", reply_markup=kb)
        return

    if "faction" not in s:
        if message.text not in FACTIONS:
            bot.send_message(message.chat.id, "❌ Выберите фракцию из предложенных кнопок.")
            return

        s["faction"] = message.text

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for k in KITS:
            kb.add(k)

        bot.send_message(message.chat.id, "Выберите kit:", reply_markup=kb)
        return

    if "kit" not in s:
        if message.text not in KITS:
            bot.send_message(message.chat.id, "❌ Выберите kit из предложенных кнопок.")
            return

        s["kit"] = message.text

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("Да ✅", "Выбрать заново ❌")

        bot.send_message(message.chat.id,
            f'{s["nick"]}, Вы выбрали:\nФракция: {s["faction"]}\nKit: {s["kit"]}\n\nПодтвердить?',
            reply_markup=kb)
        return

    if message.text == "Выбрать заново ❌":
        sessions.pop(uid)
        start(message)
        return

    if message.text == "Да ✅":
        username = message.from_user.username
        if username:
            username = f"@{username}" if not username.startswith("@") else username
        else:
            username = "unknown"
        
        user = {
            "telegram_id": uid,
            "username": username,
            "minecraft": s["nick"],
            "faction": s["faction"],
            "kit": s["kit"],
            "banned": False
        }

        db = parser.load_db()

        exists = False
        for i, u in enumerate(db["users"]):
            if u["telegram_id"] == uid:
                db["users"][i] = user
                exists = True
                break

        if not exists:
            db["users"].append(user)

        if user.get("minecraft"):
            rcon_whitelist_add(user["minecraft"])

        parser.save_db(db)

        text = (
            f"🆔 {uid}\n"
            f"🎮 {s['nick']}\n"
            f"👤 {username}\n"
            f"🏳 {s['faction']}\n"
            f"🧰 {s['kit']}\n"
            f"🚫 banned: false"
        )

        try:
            msg = bot.send_message(MIRROR_GROUP, text)
            
            db = parser.load_db()
            for u in db["users"]:
                if u["telegram_id"] == uid:
                    u["mirror_msg"] = msg.message_id
                    break
            
            parser.save_db(db)
        except Exception as e:
            print(f"Mirror send error: {e}")

        github_save_db(db, message=f"Register user {uid} ({username})")

        bot.send_message(
            chat_id,
            "✅ Регистрация завершена\n\n💡 Используйте /getcode для получения кода входа на сервер",
            reply_markup=ReplyKeyboardRemove()
        )
        log(f"NEW USER {uid} ({s['nick']})")
        sessions.pop(uid)
        return


def github_load_db():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return {"users": []}
    data = r.json()
    content = base64.b64decode(data['content']).decode()
    return json.loads(content)

def github_save_db(db, message="Update database"):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

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

        print("✅ GitHub → local DB synced")

    except Exception as e:
        print(f"❌ GitHub sync failed: {e}")


if __name__ == "__main__":
    print("🤖 BOT STARTED")
    print("📡 Flask API: http://0.0.0.0:5000")
    print("💡 Для публичного доступа используйте ngrok:")
    print("   ngrok http 5000")
    sync_github_to_local()
    bot.infinity_polling()