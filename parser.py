import json

DB_FILE = "base.jsonc"


def load_db():
    """Загружает базу данных из файла"""
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)


def save_db(data):
    """Сохраняет базу данных в файл"""
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_user(value):
    """
    Ищет пользователя по telegram_id, username или Minecraft нику.
    Возвращает словарь пользователя или None
    """
    db = load_db()
    value = str(value).lower()

    for u in db["users"]:
        if str(u.get("telegram_id", "")).lower() == value \
           or (u.get("username") and u["username"].lower() == value) \
           or (u.get("minecraft") and u["minecraft"].lower() == value):
            return u
    return None


def ban_user(value):
    """
    Бан пользователя по telegram_id, username или Minecraft нику.
    Добавляет его в db["bans"], если там ещё нет.
    """
    db = load_db()
    user = find_user(value)
    if not user:
        return False

    user["banned"] = True

    # Добавляем в bans, если там ещё нет
    if not any(b.get("telegram_id") == user.get("telegram_id") for b in db.get("bans", [])):
        db.setdefault("bans", []).append(user)

    save_db(db)
    return True


def unban_user(value):
    """
    Разбан пользователя по telegram_id, username или Minecraft нику.
    Удаляет его из db["bans"].
    """
    db = load_db()
    user = find_user(value)
    if not user:
        return False

    user["banned"] = False

    # Удаляем из bans
    db["bans"] = [b for b in db.get("bans", []) if b.get("telegram_id") != user.get("telegram_id")]

    save_db(db)
    return True


def is_banned(value):
    """
    Проверяет, забанен ли пользователь по telegram_id, username или Minecraft нику
    """
    user = find_user(value)
    return user.get("banned", False) if user else False