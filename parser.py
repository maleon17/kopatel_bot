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


def get_user(tg_id):
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            return u
    return None


def update_user(updated):
    db = load_db()
    for i, u in enumerate(db["users"]):
        if u["telegram_id"] == updated["telegram_id"]:
            db["users"][i] = updated
            break
    save_db(db)


def ban_user(tg_id):
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            u["banned"] = True
    save_db(db)


def unban_user(tg_id):
    db = load_db()
    for u in db["users"]:
        if u["telegram_id"] == tg_id:
            u["banned"] = False
    save_db(db)


def is_banned(tg_id):
    u = get_user(tg_id)
    return u and u.get("banned", False)

def find_user(value):
    db = load_db()

    value = str(value).lower()

    for u in db["users"]:
        if (
            str(u["telegram_id"]) == value
            or u["minecraft"].lower() == value
            or (u["username"] and u["username"].lower() == value)
        ):
            return u

    for b in db["bans"]:
        if (
            str(b["telegram_id"]) == value
            or b["minecraft"].lower() == value
            or (b["username"] and b["username"].lower() == value)
        ):
            return b

    return None