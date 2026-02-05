import json

DB_FILE = "base.jsonc"


def load_db():
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_user(user):
    db = load_db()
    db["users"].append(user)
    save_db(db)


def user_exists(tg_id):
    db = load_db()
    return any(u["telegram_id"] == tg_id for u in db["users"])