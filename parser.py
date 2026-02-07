import json

DB_FILE = "base.jsonc"

def load_db():
    """Загрузка базы"""
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)

def save_db(data):
    """Сохранение базы"""
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def find_user(value):
    """Ищет пользователя по telegram_id, username или minecraft нику"""
    db = load_db()
    value = str(value).lower()
    for u in db["users"]:
        if str(u["telegram_id"]) == value \
           or (u.get("username") and u["username"].lower() == value) \
           or (u.get("minecraft") and u["minecraft"].lower() == value):
            return u
    return None

def add_user(user):
    """Добавляет нового пользователя или обновляет существующего"""
    db = load_db()
    exists = False
    for i, u in enumerate(db["users"]):
        if u["telegram_id"] == user["telegram_id"]:
            db["users"][i] = user
            exists = True
            break
    if not exists:
        db["users"].append(user)
    save_db(db)

def ban_user(value):
    """Бан пользователя по id / username / minecraft"""
    db = load_db()
    user = find_user(value)
    if not user:
        return False
    # Меняем поле banned
    for u in db["users"]:
        if u["telegram_id"] == user["telegram_id"]:
            u["banned"] = True
            break
    save_db(db)
    return True

def unban_user(value):
    """Разбан пользователя по id / username / minecraft"""
    db = load_db()
    user = find_user(value)
    if not user:
        return False
    for u in db["users"]:
        if u["telegram_id"] == user["telegram_id"]:
            u["banned"] = False
            break
    save_db(db)
    return True

def is_banned(tg_id):
    """Проверка, забанен ли пользователь по telegram_id"""
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            return u.get("banned", False)
    return False

def mirror_load_db(bot, mirror_group):
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

    save_db(db)
    print("✅ База восстановлена из зеркала")