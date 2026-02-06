import json

DB_FILE = "base.jsonc"

def load_db():
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)

def save_db(data):
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

def ban_user(value):
    db = load_db()
    user = find_user(value)
    if not user:
        return False
    user["banned"] = True
    save_db(db)  # обязательно сохраняем базу после изменения
    return True

def unban_user(value):
    db = load_db()
    user = find_user(value)
    if not user:
        return False
    user["banned"] = False
    save_db(db)
    return True

def is_banned(tg_id):
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            return u.get("banned", False)
    return False

def add_user(user):
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