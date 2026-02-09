print("=== Starting bot ===")

import sys
print("✓ sys imported")

import telebot
print("✓ telebot imported")

import requests
import base64
import json
import time
import logging 
import queue
import threading
import multiprocessing
print("✓ standard libraries imported")

from mcrcon import MCRcon
print("✓ mcrcon imported")

from telebot import types
print("✓ telebot.types imported")

import parser
from parser import ban_user, unban_user, find_user, is_banned, add_user
print("✓ parser imported")

from logger import log
print("✓ logger imported")

from telebot.types import ReplyKeyboardRemove
print("✓ ReplyKeyboardRemove imported")

from config import BOT_TOKEN, ADMINS, FACTIONS, KITS, MIRROR_GROUP, RCON_HOST, RCON_PORT, RCON_PASSWORD
print("✓ config imported")

# GitHub импорт - делаем опциональным
try:
    sys.path.append("/data/data/com.termux/files/home/github_lib")
    from github import GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE
    GITHUB_ENABLED = True
    print("✓ github imported (enabled)")
except ImportError:
    print("⚠ github.py not found - trying local")
    try:
        from github import GITHUB_TOKEN, GITHUB_REPO, GITHUB_FILE
        GITHUB_ENABLED = True
        print("✓ github imported from local (enabled)")
    except ImportError:
        print("⚠ github.py not found - GitHub sync disabled")
        GITHUB_ENABLED = False
        GITHUB_TOKEN = None
        GITHUB_REPO = None
        GITHUB_FILE = None


logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("telebot").setLevel(logging.CRITICAL)
print("✓ logging configured")

bot = telebot.TeleBot(BOT_TOKEN)
print("✓ bot initialized")

sessions = {}

# ----------------- RCON PROCESS -------------------

# Очередь команд для процесса
rcon_queue = multiprocessing.Queue()

def rcon_process_worker(queue, host, port, password):
    """Процесс для выполнения команд RCON"""
    while True:
        cmd = queue.get()
        if cmd is None:  # сигнал для завершения процесса
            break
        try:
            action = cmd[0]
            
            # Для custom команды второй параметр - сама команда целиком
            if action == "custom":
                command = cmd[1]
                with MCRcon(host, password, port=port) as mcr:
                    resp = mcr.command(command)
                    print(f"RCON: {command} -> {resp}")
                continue
            
            # Для остальных команд второй параметр - ник
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
                elif action == "kick":
                    reason = cmd[2] if len(cmd) > 2 else "Kicked"
                    resp = mcr.command(f"kick {nick} {reason}")
                    print(f"RCON: kick {nick} -> {resp}")
                elif action == "clearsession":
                    resp = mcr.command(f"authmod clearsession {nick}")
                    print(f"RCON: authmod clearsession {nick} -> {resp}")
        except Exception as e:
            print("RCON ERROR:", e)

# Запуск процесса один раз при старте бота
print("Starting RCON process...")
rcon_process = multiprocessing.Process(
    target=rcon_process_worker, 
    args=(rcon_queue, RCON_HOST, RCON_PORT, RCON_PASSWORD),
    daemon=True
)
rcon_process.start()
print("✓ RCON process started")

# --------- Функции для добавления команд в очередь ---------

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
    """Отправка произвольной команды через RCON"""
    rcon_queue.put(("custom", command))

def rcon_kick(nick, reason="Kicked"):
    rcon_queue.put(("kick", nick, reason))

def rcon_clearsession(nick):
    rcon_queue.put(("clearsession", nick))


@bot.message_handler(commands=["start"])
def start(message):
    if GITHUB_ENABLED:
        try:
            sync_github_to_local()
            db = github_load_db()
        except Exception as e:
            print("GitHub load error:", e)
            db = {"users": []}
    else:
        db = parser.load_db()

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
        if user.get("minecraft"):
            rcon_ban(user["minecraft"]) 

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
        if GITHUB_ENABLED:
            github_save_db(db, message=f"Ban user {uid}")
            signal_mod_reload()  # Сигнал моду обновить базу
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
        if user.get("minecraft"):
            rcon_unban(user["minecraft"])

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
        if GITHUB_ENABLED:
            github_save_db(db, message=f"Unban user {uid}")
            signal_mod_reload()  # Сигнал моду обновить базу
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
    if GITHUB_ENABLED:
        github_save_db(db, message=f"Delete user {uid}")
        signal_mod_reload()  # Сигнал моду обновить базу

    if user.get("minecraft"):
        rcon_del_user(user["minecraft"])

    bot.send_message(
        message.chat.id,
        f'🗑 Пользователь <a href="tg://user?id={uid}">{name}</a> полностью удалён.',
        parse_mode="HTML"
    )

# ---------------- SYNC WHITELIST ----------------
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
        # Пропускаем забаненных
        if user.get("banned", False):
            continue
        
        # Пропускаем пользователей без Minecraft ника
        if not user.get("minecraft"):
            continue
        
        try:
            rcon_whitelist_add(user["minecraft"])
            added_count += 1
            time.sleep(0.1)  # небольшая задержка между командами
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

# ---------------- OP ----------------
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

# ---------------- DEOP ----------------
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

#----------------- SERVER RESTART-----------------
@bot.message_handler(commands=["srvrestart"])
def cmd_srvrestart(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return
    
    bot.reply_to(message, "⚠️ Отправляю оповещение о перезагрузке...")
    
    def restart_countdown():
        # Главное предупреждение
        rcon_custom_command('title @a title {"text":"ВНИМАНИЕ!","color":"red","bold":true}')
        rcon_custom_command('title @a subtitle {"text":"Перезагрузка через 5 секунд","color":"yellow"}')
        time.sleep(2)
        
        # Отсчёт
        rcon_custom_command('title @a title {"text":"5","color":"yellow","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"4","color":"yellow","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"3","color":"gold","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"2","color":"red","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"1","color":"dark_red","bold":true}')
        time.sleep(1)
        
        # Финальное сообщение
        rcon_custom_command('title @a title {"text":"ПЕРЕЗАГРУЗКА","color":"dark_red","bold":true}')
        rcon_custom_command('title @a subtitle {"text":"Сервер скоро вернётся","color":"gray"}')
    
    thread = threading.Thread(target=restart_countdown)
    thread.start()
    
    log(f"Server restart countdown by {message.from_user.id}")

# ---------------- CUSTOM COMMAND ----------------
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
    
    # Разбиваем команду на слова
    words = command.split()
    db = parser.load_db()
    
    # Проходим по каждому слову и пытаемся найти пользователя
    converted_words = []
    conversions = []  # для логирования
    
    for word in words:
        user = find_user(word)
        if user and user.get("minecraft"):
            # Нашли пользователя - заменяем на его Minecraft ник
            converted_words.append(user["minecraft"])
            conversions.append(f"{word} → {user['minecraft']}")
        else:
            # Не нашли - оставляем как есть
            converted_words.append(word)
    
    # Собираем команду обратно
    final_command = " ".join(converted_words)
    
    # Отправляем команду
    rcon_custom_command(final_command)
    
    # Формируем ответ
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

    # Игнорируем сообщения в группах
    if message.chat.type != "private":
        return

    if parser.is_banned(uid):
        return

    if uid not in sessions:
        return

    s = sessions[uid]

    # ник
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

    # фракция
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

    # kit
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

    # подтверждение
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

        if user.get("minecraft"):
            rcon_whitelist_add(user["minecraft"])

        # Сохраняем базу
        parser.save_db(db)

        text = (
            f"🆔 {uid}\n"
            f"🎮 {s['nick']}\n"
            f"👤 {username}\n"
            f"🏳 {s['faction']}\n"
            f"🧰 {s['kit']}\n"
            f"🚫 banned: false"
        )

        # Отправляем в зеркальную группу
        try:
            msg = bot.send_message(MIRROR_GROUP, text)
            
            # Сохраняем ID сообщения в зеркале
            db = parser.load_db()
            for u in db["users"]:
                if u["telegram_id"] == uid:
                    u["mirror_msg"] = msg.message_id
                    break
            
            parser.save_db(db)
        except Exception as e:
            print(f"Mirror send error: {e}")

        # Синхронизируем с GitHub
        if GITHUB_ENABLED:
            github_save_db(db, message=f"Register user {uid} ({username})")
            signal_mod_reload()  # Сигнал моду обновить базу

        bot.send_message(
            chat_id,
            "✅ Регистрация завершена",
            reply_markup=ReplyKeyboardRemove()
        )
        log(f"NEW USER {uid} ({s['nick']})")
        sessions.pop(uid)
        return


def github_load_db():
    """Загрузка базы данных из GitHub"""
    if not GITHUB_ENABLED:
        return {"users": []}
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return {"users": []}  # если файла нет
    data = r.json()
    content = base64.b64decode(data['content']).decode()
    return json.loads(content)

def github_save_db(db, message="Update database"):
    """Сохранение базы данных в GitHub"""
    if not GITHUB_ENABLED:
        return False
    
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
    """Синхронизация базы данных из GitHub в локальный файл"""
    if not GITHUB_ENABLED:
        print("⚠ GitHub sync disabled")
        return
    
    try:
        db = github_load_db()

        with open("base.jsonc", "w", encoding="utf8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

        print("✅ GitHub → local DB synced")

    except Exception as e:
        print(f"❌ GitHub sync failed: {e}")


# ============== AUTH SYSTEM ==============


def signal_mod_reload():
   # """Сигнал моду перечитать базу данных через RCON"""
    rcon_custom_command("authmod reload")

@bot.callback_query_handler(func=lambda call: call.data.startswith("kick_"))
def handle_not_me_kick(call):
   # """Обработка кнопки 'Это не я ⚠️'"""
    try:
        nick = call.data.replace("kick_", "")
        
        user = find_user(nick)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден")
            return
        
        # Через очередь — никаких проблем с потоками
        rcon_kick(nick, "Сессия отклонена владельцем аккаунта")
        rcon_clearsession(nick)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🚫 Игрок {nick} кикнут с сервера.\n\n"
                 f"Сессия сброшена. При следующем входе потребуется код подтверждения."
        )
        
        bot.answer_callback_query(call.id, "✅ Игрок кикнут!")
        log(f"Player {nick} kicked by owner (telegram_id: {call.from_user.id})")
        
    except Exception as e:
        print(f"Error in handle_not_me_kick: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка")


if __name__ == "__main__":
    print("🤖 BOT STARTING...")
    
    # Проверяем наличие base.jsonc
    try:
        with open("base.jsonc", "r", encoding="utf8") as f:
            json.load(f)
        print("✓ base.jsonc found and valid")
    except FileNotFoundError:
        print("⚠ base.jsonc not found, creating empty...")
        with open("base.jsonc", "w", encoding="utf8") as f:
            json.dump({"users": []}, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ base.jsonc error: {e}")
    
    if GITHUB_ENABLED:
        sync_github_to_local()
    
    print("🤖 BOT STARTED - waiting for messages...")
    bot.infinity_polling()
