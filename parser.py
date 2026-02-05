import json

DB_FILE = "base.jsonc"


def load_db():
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ───── USERS ─────

def add_user(user):
    db = load_db()
    db["users"].append(user)
    save_db(db)


def user_exists(tg_id):
    db = load_db()
    return any(u["telegram_id"] == tg_id for u in db["users"])


def get_user(tg_id):
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            return u
    return None


# ───── BANS ─────

def is_banned(tg_id):
    db = load_db()
    return any(b["telegram_id"] == tg_id for b in db["bans"])


def ban_user(user):
    db = load_db()

    db["bans"].append(user)

    db["users"] = [u for u in db["users"] if u["telegram_id"] != user["telegram_id"]]

    save_db(db)


def unban_user(tg_id):
    db = load_db()
    db["bans"] = [b for b in db["bans"] if b["telegram_id"] != tg_id]
    save_db(db)