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
    
    # Добавляем @ если его нет (для поиска по username)
    value_with_at = f"@{value}" if not value.startswith("@") else value
    value_without_at = value[1:] if value.startswith("@") else value
    
    for u in db["users"]:
        # Поиск по telegram_id
        if str(u["telegram_id"]) == value:
            return u
        
        # Поиск по username (с @ и без)
        if u.get("username"):
            username_lower = u["username"].lower()
            if username_lower == value_with_at or username_lower == value_without_at:
                return u
        
        # Поиск по minecraft нику
        if u.get("minecraft") and u["minecraft"].lower() == value:
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
