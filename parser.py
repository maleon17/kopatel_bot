import json

DB_FILE = "base.jsonc"

def load_db():
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def find_user(value):
    """Ищет пользователя по tg_id, username или minecraft нику"""
    db = load_db()
    value = str(value).lower()

    for u in db["users"]:
        if str(u["telegram_id"]) == value \
           or (u.get("username") and u["username"].lower() == value) \
           or (u.get("minecraft") and u["minecraft"].lower() == value):
            return u
    return None

def ban_user(value):
    """Бан по id / username / minecraft"""
    db = load_db()
    user = find_user(value)
    if not user:
        return False

    user["banned"] = True
    # Если пользователя ещё нет в bans, добавим
    if user not in db["bans"]:
        db["bans"].append(user)
    save_db(db)
    return True

def unban_user(value):
    """Разбан по id / username / minecraft"""
    db = load_db()
    user = find_user(value)
    if not user:
        return False

    user["banned"] = False
    # Удаляем пользователя из bans
    db["bans"] = [b for b in db["bans"] if b["telegram_id"] != user["telegram_id"]]
    save_db(db)
    return True

def is_banned(tg_id):
    """Проверяет, забанен ли пользователь по telegram_id"""
    user = get_user(tg_id)
    return user.get("banned", False) if user else False