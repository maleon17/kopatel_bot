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
                    resp# = mcr.command(f"whitelist remove {nick}")
                    #print(f"RCON: del {nick} -> {resp}")
                elif action == "whitelist":
                    resp# = mcr.command(f"whitelist add {nick}")
                    #print(f"RCON: whitelist add {nick} -> {resp}")
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

# -------- добавление команд в очередь ---------

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

def rcon_get_response(command):
    """Выполняет RCON команду и возвращает ответ через отдельный процесс"""
    result_queue = multiprocessing.Queue()
    
    def worker():
        try:
            with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
                resp = mcr.command(command)
                result_queue.put(resp)
        except Exception as e:
            print(f"RCON response error: {e}")
            result_queue.put(None)
    
    proc = multiprocessing.Process(target=worker)
    proc.start()
    proc.join(timeout=5)
    
    if proc.is_alive():
        proc.kill()
        return None
    
    try:
        return result_queue.get_nowait()
    except:
        return None

# ------------ convert fraction name -----------

def convert_faction(faction_name):
    """Конвертирует название фракции в значение для команды"""
    faction_map = {
        "🔴 Красные": "red",
        "🔵 Синие": "blue",
    }
    return faction_map.get(faction_name)

def convert_kit(kit_name):
    """Конвертирует название кита в значение для команды"""
    kit_map = {
        "🪖 Воин": "boec",
        "🎯 Снайпер": "sniper",
        "🛠 Инженер": "ingener",
        "🚁 Оператор БПЛА": "operator_bpla",
        "👨‍⚕️ Медик": "medik",
    }
    return kit_map.get(kit_name)

# ------------ faction balance -----------

def get_faction_counts():
    db = parser.load_db()
    counts = {}
    for faction in FACTIONS:
        counts[faction] = 0
    for user in db["users"]:
        if user.get("banned", False):
            continue
        faction = user.get("faction")
        if faction in counts:
            counts[faction] += 1
    return counts

def is_faction_available(chosen_faction):
    counts = get_faction_counts()
    MAX_DIFFERENCE = 5
    chosen_count = counts.get(chosen_faction, 0)
    for faction, count in counts.items():
        if faction != chosen_faction:
            if chosen_count - count >= MAX_DIFFERENCE:
                return False
    return True

# --------------- START --------------------

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

    if message.chat.type != "private":
        return

    uid = message.from_user.id
    existing = find_user(uid)

    if existing:
        bot.send_message(
            message.chat.id,
            f"Пользователь уже зарегистрирован ❌\n"
            f"{existing['minecraft']}, вы выбрали:\n"
            f"Фракция: {existing['faction']}\n"
            f"Kit: {existing['kit']}"
        )
        send_main_menu(message.chat.id)  # отдельной строкой, после send_message
        return

    sessions[uid] = {}
    bot.send_message(
        message.chat.id,
        "🛰 Первичный допуск\n======================\n"
        "Введите Minecraft ник (3–16 символов, без пробелов)",
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

# ---------------- ONLINE ----------------

@bot.message_handler(commands=["online"])
def cmd_online(message):
    def get_online():
        try:
            response = rcon_get_response("list")

            if response is None:
                bot.send_message(message.chat.id, "🔴 Сервер выключен")
                return

            if ":" in response:
                players_part = response.split(":")[-1].strip()
                if players_part:
                    online_nicks = [n.strip() for n in players_part.split(",") if n.strip()]
                else:
                    online_nicks = []
            else:
                online_nicks = []

            if not online_nicks:
                bot.send_message(message.chat.id, "📡 На сервере никого нет")
                return

            db = parser.load_db()
            factions = {}
            for faction in FACTIONS:
                factions[faction] = []

            unknown = []

            for nick in online_nicks:
                found = False
                for user in db["users"]:
                    if user.get("minecraft", "").lower() == nick.lower():
                        faction = user.get("faction", "")
                        kit = user.get("kit", "—")
                        if faction in factions:
                            factions[faction].append(f"{kit} - {user['minecraft']}")
                        else:
                            unknown.append(nick)
                        found = True
                        break
                if not found:
                    unknown.append(nick)

            text = f"📡 Онлайн: {len(online_nicks)}\n\n"

            for faction in FACTIONS:
                players = factions[faction]
                text += f"{faction}:\n"
                if players:
                    for p in players:
                        text += f"  {p}\n"
                else:
                    text += "  Никого\n"
                text += "\n"

            if unknown:
                text += "❓ Не в базе:\n"
                for nick in unknown:
                    text += f"  {nick}\n"

            bot.send_message(message.chat.id, text)

        except Exception as e:
            print(f"Online check error: {e}")
            bot.send_message(message.chat.id, "🔴 Сервер выключен")

    thread = threading.Thread(target=get_online)
    thread.start()

# ---------------- MIRROR RESTART ----------------

@bot.message_handler(commands=["restartmirror"])
def cmd_restart_mirror(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    bot.send_message(message.chat.id, "⏳ Перезапуск зеркальной группы...")

    db = parser.load_db()

    # Шаг 1: Удаляем все старые сообщения
    deleted_count = 0
    for user in db["users"]:
        msg_id = user.get("mirror_msg")
        if msg_id:
            try:
                bot.delete_message(MIRROR_GROUP, msg_id)
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting msg {msg_id}: {e}")
            time.sleep(0.1)

    bot.send_message(message.chat.id, f"🗑 Удалено сообщений: {deleted_count}\n⏳ Создаю новые...")

    # Шаг 2: Отправляем новые сообщения для каждого пользователя
    created_count = 0
    error_count = 0

    for user in db["users"]:
        try:
            username = user.get("username", "unknown")
            nick = user.get("minecraft", "—")
            faction = user.get("faction", "—")
            kit = user.get("kit", "—")
            banned = user.get("banned", False)
            uid = user.get("telegram_id", "—")

            text = (
                f"🆔 {uid}\n"
                f"🎮 {nick}\n"
                f"👤 {username}\n"
                f"🏳 {faction}\n"
                f"🧰 {kit}\n"
                f"🚫 banned: {str(banned).lower()}"
            )

            msg = bot.send_message(MIRROR_GROUP, text)
            user["mirror_msg"] = msg.message_id
            created_count += 1
            time.sleep(0.3)  # задержка чтобы не словить flood limit

        except Exception as e:
            print(f"Error creating mirror for {user.get('minecraft', '?')}: {e}")
            error_count += 1

    # Шаг 3: Сохраняем обновлённую базу
    parser.save_db(db)

    # Синхронизируем с GitHub
    if GITHUB_ENABLED:
        github_save_db(db, message="Restart mirror group")

    bot.send_message(
        message.chat.id,
        f"✅ Зеркальная группа перезапущена!\n\n"
        f"📊 Статистика:\n"
        f"• Удалено старых: {deleted_count}\n"
        f"• Создано новых: {created_count}\n"
        f"• Ошибок: {error_count}\n"
        f"• Всего в базе: {len(db['users'])}"
    )

    log(f"Mirror restart: {deleted_count} deleted, {created_count} created (by {message.from_user.id})")
    
# ---------------- SYNC ----------------

@bot.message_handler(commands=["sync"])
def cmd_sync_whitelist(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "❌ У вас нет прав для этой команды.")
        return

    bot.send_message(message.chat.id, "⏳ Синхронизация whitelist и китов...")

    db = parser.load_db()
    
    #whitelist_count = 0
    kit_count = 0
    skipped_count = 0
    error_count = 0
    
    for user in db["users"]:
        # Пропускаем забаненных
        if user.get("banned", False):
            skipped_count += 1
            continue
        
        # Пропускаем пользователей без Minecraft ника
        if not user.get("minecraft"):
            skipped_count += 1
            continue
        
        nick = user["minecraft"]
        
        # Whitelist
        #try:
        #    rcon_whitelist_add(nick)
        #    whitelist_count += 1
        #    time.sleep(0.1)
        #except Exception as e:
        #    print(f"Error adding {nick} to whitelist: {e}")
        #    error_count += 1
        
        # Кит
        faction = convert_faction(user.get("faction", ""))
        kit = convert_kit(user.get("kit", ""))
        
        if faction and kit:
            try:
                rcon_custom_command(f"addkit {nick} {faction} {kit}")
                rcon_custom_command(f"team join {faction} {nick}")
                kit_count += 1
                time.sleep(0.1)
            except Exception as e:
                print(f"Error adding kit for {nick}: {e}")
                error_count += 1
        else:
            print(f"Skipping kit for {nick}: faction={user.get('faction')} kit={user.get('kit')}")
    
    bot.send_message(
        message.chat.id,
        f"✅ Синхронизация завершена!\n\n"
        f"📊 Статистика:\n"
        #f"• Добавлено в whitelist: {whitelist_count}\n"
        f"• Выдано китов: {kit_count}\n"
        f"• Пропущено: {skipped_count}\n"
        f"• Ошибок: {error_count}\n"
        f"• Всего в базе: {len(db['users'])}\n"
        f"• Забанено: {sum(1 for u in db['users'] if u.get('banned', False))}"
    )
    
    log(f"Sync kits: {kit_count} kits assigned (by {message.from_user.id})")
 
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
        time.sleep(2)
        
        # Отсчёт
        rcon_custom_command('title @a title {"text":"Перезагрузка через 5 секунд","color":"yellow","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"Перезагрузка через 4 секунд","color":"yellow","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"Перезагрузка через 3 секунд","color":"gold","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"Перезагрузка через 2 секунд","color":"red","bold":true}')
        time.sleep(1)
        rcon_custom_command('title @a title {"text":"Перезагрузка через 1 секунд","color":"dark_red","bold":true}')
        time.sleep(1)
        
        # Финальное сообщение
        rcon_custom_command('title @a title {"text":"ПЕРЕЗАГРУЗКА","color":"dark_red","bold":true}')
        rcon_custom_command('title @a subtitle {"text":"Сервер скоро вернётся","color":"gray"}')
    
    thread = threading.Thread(target=restart_countdown)
    thread.start()
    
    log(f"Server restart countdown by {message.from_user.id}")

# ---------------- CUSTOM COMMAND ----------------

@bot.message_handler(commands=["cmd"])
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

# ============== ГЛАВНОЕ МЕНЮ ==============

def send_main_menu(chat_id):
    """Отправляет главное меню"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔧 Инструменты")
    kb.row("🆘 Поддержка")
    bot.send_message(chat_id, "📋 Главное меню:", reply_markup=kb)

# ============== ИНСТРУМЕНТЫ ==============

@bot.message_handler(func=lambda m: m.text == "🔧 Инструменты")
def menu_tools(message):
    if message.chat.type != "private":
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎤 Микрофон", "🔐 VPN")
    kb.row("📦 Сборка")
    kb.row("◀️ Назад")
    bot.send_message(message.chat.id, "🔧 Инструменты:", reply_markup=kb)

# ============== МИКРОФОН ==============

@bot.message_handler(func=lambda m: m.text == "🎤 Микрофон")
def menu_microphone(message):
    if message.chat.type != "private":
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📖 Инструкция по микрофону", url="https://t.me/copalpal/89"))
    bot.send_message(
        message.chat.id,
        "🎤 *Настройка микрофона*\n\n"
        "Нажмите кнопку ниже для просмотра инструкции:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ============== VPN ==============

@bot.message_handler(func=lambda m: m.text == "🔐 VPN")
def menu_vpn(message):
    if message.chat.type != "private":
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📖 Инструкция по VPN", url="https://t.me/copalpal/59?single"))
    bot.send_message(
        message.chat.id,
        "🔐 *Настройка VPN*\n\n"
        "Нажмите кнопку ниже для просмотра инструкции:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ============== СБОРКА ==============

@bot.message_handler(func=lambda m: m.text == "📦 Сборка")
def menu_build(message):
    if message.chat.type != "private":
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("⚙️ Настройка", "📥 Скачать")
    kb.row("◀️ Назад в инструменты")
    bot.send_message(message.chat.id, "📦 Сборка:", reply_markup=kb)

# ============== НАСТРОЙКА СБОРКИ ==============

@bot.message_handler(func=lambda m: m.text == "⚙️ Настройка")
def menu_build_setup(message):
    if message.chat.type != "private":
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("TLauncher", "Prism/Freesm")
    kb.row("◀️ Назад в сборку")
    bot.send_message(message.chat.id, "⚙️ Выберите ваш лаунчер:", reply_markup=kb)

# ============== TLAUNCHER ==============

@bot.message_handler(func=lambda m: m.text == "TLauncher")
def menu_tlauncher(message):
    if message.chat.type != "private":
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📖 Настройка для TLauncher", url="https://t.me/copalpal/119?single"))
    bot.send_message(
        message.chat.id,
        "⚙️ *Настройка сборки для TLauncher*\n\n"
        "Нажмите кнопку ниже для просмотра инструкции:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ============== PRISM/FREESM ==============

@bot.message_handler(func=lambda m: m.text == "Prism/Freesm")
def menu_prism(message):
    if message.chat.type != "private":
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📖 Настройка для Prism/FreeSM", url="https://t.me/copalpal/124?single"))
    bot.send_message(
        message.chat.id,
        "⚙️ *Настройка сборки для Prism/Freesm*\n\n"
        "Нажмите кнопку ниже для просмотра инструкции:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ============== СКАЧАТЬ СБОРКУ ==============

@bot.message_handler(func=lambda m: m.text == "📥 Скачать")
def menu_build_download(message):
    if message.chat.type != "private":
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("Google Диск ❌", url="https://example.com"),
        types.InlineKeyboardButton("Yandex Диск ❌", url="https://example.com")
    )
    kb.row(
        types.InlineKeyboardButton("Telegram ✅", url="https://t.me/copalpal/148")
    )
    bot.send_message(
        message.chat.id,
        "📥 *Скачать сборку*\n\n"
        "Выберите откуда скачать:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ============== НАЗАД ==============

@bot.message_handler(func=lambda m: m.text == "◀️ Назад")
def menu_back_main(message):
    if message.chat.type != "private":
        return
    send_main_menu(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "◀️ Назад в инструменты")
def menu_back_tools(message):
    if message.chat.type != "private":
        return
    menu_tools(message)

@bot.message_handler(func=lambda m: m.text == "◀️ Назад в сборку")
def menu_back_build(message):
    if message.chat.type != "private":
        return
    menu_build(message)

# ============== ПОДДЕРЖКА ==============

@bot.message_handler(func=lambda m: m.text == "🆘 Поддержка")
def menu_support(message):
    if message.chat.type != "private":
        return
    bot.send_message(message.chat.id, "🆘 Раздел поддержки в разработке...")

# ---------- ПОДСЧЁТ ФРАКЦИЙ -----------

def get_faction_counts():
    """Считает количество игроков в каждой фракции"""
    db = parser.load_db()
    counts = {}
    for faction in FACTIONS:
        counts[faction] = 0
    
    for user in db["users"]:
        if user.get("banned", False):
            continue
        faction = user.get("faction")
        if faction in counts:
            counts[faction] += 1
    
    return counts

def is_faction_available(chosen_faction):
    """Проверяет можно ли присоединиться к фракции"""
    counts = get_faction_counts()
    MAX_DIFFERENCE = 5
    
    chosen_count = counts.get(chosen_faction, 0)
    
    for faction, count in counts.items():
        if faction != chosen_faction:
            # Если выбранная фракция уже больше другой на MAX_DIFFERENCE
            if chosen_count - count >= MAX_DIFFERENCE:
                return False
    
    return True

# ---------------- flow ----------------

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

        # Проверяем баланс фракций
        if not is_faction_available(message.text):
            counts = get_faction_counts()
            counts_text = "\n".join([f"  {f}: {c} чел." for f, c in counts.items()])
            bot.send_message(
                message.chat.id,
                f"⚠️ Перевес по количеству игроков во фракции!\n\n"
                f"📊 Текущий баланс:\n{counts_text}\n\n"
                f"Выберите другую фракцию."
            )
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

        if not exists:
            db["users"].append(user)

        if user.get("minecraft"):
            rcon_whitelist_add(user["minecraft"])
            
            # === АВТОВЫДАЧА КИТА ===
            nick = s["nick"]
            faction = convert_faction(s["faction"])
            kit = convert_kit(s["kit"])
            
            if faction and kit:
                rcon_custom_command(f"addkit {nick} {faction} {kit}")
                print(f"Kit assigned: {nick} {faction} {kit}")
                
                # === ПРИВЯЗКА К КОМАНДЕ ===
                rcon_custom_command(f"team join {faction} {nick}")
                print(f"Team assigned: {nick} -> {faction}")


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

        bot.send_message(chat_id, "✅ Регистрация завершена")
        send_main_menu(chat_id)
            
        log(f"NEW USER {uid} ({s['nick']})")
        sessions.pop(uid)
        return

# -------------- github load ------------------

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


# --------------- AUTH SYSTEM -----------------


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

    # Команды для простых смертных
    bot.set_my_commands([
        telebot.types.BotCommand("start", "Регистрация"),
        telebot.types.BotCommand("online", "Кто на сервере"),
    ])

    # Команды для админов
    admin_commands = [
        telebot.types.BotCommand("start", "Регистрация"),
        telebot.types.BotCommand("online", "Кто на сервере"),
        telebot.types.BotCommand("ban", "Забанить игрока"),
        telebot.types.BotCommand("unban", "Разбанить игрока"),
        telebot.types.BotCommand("deluser", "Удалить игрока"),
        telebot.types.BotCommand("op", "Выдать OP"),
        telebot.types.BotCommand("deop", "Забрать OP"),
        telebot.types.BotCommand("sync", "Синхронизация китов"),
        telebot.types.BotCommand("cmd", "Команда на сервер"),
        telebot.types.BotCommand("srvrestart", "Оповещение о рестарте"),
        telebot.types.BotCommand("restartmirror", "Перезапуск зеркала"),
    ]

    for admin_id in ADMINS:
        try:
            bot.set_my_commands(
                admin_commands,
                scope=telebot.types.BotCommandScopeChat(admin_id)
            )
        except Exception as e:
            print(f"Error setting admin commands for {admin_id}: {e}")
            
    print("🤖 BOT STARTED - waiting for messages...")
    bot.infinity_polling()
