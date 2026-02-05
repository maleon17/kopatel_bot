import telebot
from telebot import types
from config import BOT_TOKEN
from parser import add_user, user_exists
from parser import add_user, user_exists, is_banned, ban_user, get_user, unban_user
from config import ADMINS

bot = telebot.TeleBot(BOT_TOKEN)

# FSM
states = {}

WAIT_NICK = "nick"
WAIT_FACTION = "faction"
WAIT_KIT = "kit"
WAIT_CONFIRM = "confirm"

temp = {}


# ───────── keyboards ─────────

def post_whitelist(bot, chat_id, user):
    msg = bot.send_message(
        chat_id,
        f'@{user["username"] or "unknown"} (tg://user?id={user["telegram_id"]}) {user["minecraft_nick"]}',
        message_thread_id=WHITELIST_TOPIC_ID
    )
    return msg.message_id


def post_banlist(bot, chat_id, user):
    msg = bot.send_message(
        chat_id,
        f'@{user["username"] or "unknown"} (tg://user?id={user["telegram_id"]}) {user["minecraft_nick"]}',
        message_thread_id=BANLIST_TOPIC_ID
    )
    return msg.message_id


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎮 Подать заявку")
    kb.add("📥 Скачать сборку", "ℹ️ Информация")
    return kb


def faction_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔴 Красные", "🔵 Синие")
    return kb


def kit_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        "🪖 Воин",
        "🎯 Снайпер",
        "🛠 Инженер",
        "🚁 Оператор БПЛА",
        "👨‍⚕️ Медик"
    )
    return kb


def confirm_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Да ✅", "Выбрать заново ❌")
    return kb


# ───────── /start ─────────

@bot.message_handler(commands=["start"])
def start(m):

    if is_banned(m.from_user.id):
        bot.send_message(m.chat.id, "🚫 Вам запрещён доступ.")
        return

    if user_exists(m.from_user.id):
        bot.send_message(m.chat.id, "Вы уже зарегистрированы.")
        return

    states[m.from_user.id] = WAIT_NICK

    bot.send_message(
        m.chat.id,
        "🛰 Первичный допуск\n======================\nВведите Minecraft ник (3–16 символов, без пробелов)"
    )

# ────────── /ban ──────────

@bot.message_handler(commands=["ban"])
def ban(m):
    if m.from_user.id not in ADMINS:
        return

    if not m.reply_to_message:
        bot.send_message(m.chat.id, "Ответь командой на сообщение игрока.")
        return

    target = m.reply_to_message.from_user.id
    user = get_user(target)

    if not user:
        bot.send_message(m.chat.id, "Игрок не найден.")
        return

    # удаляем из whitelist
    if "message_id" in user:
        bot.delete_message(chat_id=GROUP_ID, message_id=user["message_id"])

    ban_user(user)  # сохраняем в базу

    # отправляем в banlist
    message_id = post_banlist(bot, GROUP_ID, user)

    bot.send_message(m.chat.id, f'🚫 {user["minecraft_nick"]} забанен.')

# ────────── /unban ──────────

@bot.message_handler(commands=["unban"])
def unban(m):
    if m.from_user.id not in ADMINS:
        bot.reply_to(m, "❌ У вас нет прав.")
        return

    # Определяем кого разбаниваем
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        user = parser.get_user(target_id)  # из parser.py
    else:
        args = m.text.split()
        if len(args) < 2:
            bot.reply_to(m, "Используйте: /unban <MinecraftNick>")
            return
        user = parser.get_user_by_minecraft(args[1])

    if not user or not parser.is_banned(user):
        bot.reply_to(m, "❌ Этот игрок не забанен.")
        return

    # удаляем из banlist
    if "message_id" in user:
        try:
            bot.delete_message(chat_id=GROUP_ID, message_id=user["message_id"])
        except Exception as e:
            print(f"Ошибка при удалении из banlist: {e}")

    # разбан в базе
    parser.unban_user(user)

    # добавляем обратно в whitelist
    message_id = post_whitelist(bot, GROUP_ID, user)
    user["message_id"] = message_id
    parser.update_user(user)  # обновляем message_id в базе

    bot.reply_to(m, f"✅ {user['minecraft_nick']} разбанен и добавлен обратно в whitelist.")

# ───────── TEXT HANDLER ─────────

@bot.message_handler(content_types=["text"])
def handler(m):
    uid = m.from_user.id
    text = m.text

    if uid not in states:
        return

    # ─ Nick
    if states[uid] == WAIT_NICK:
        if not text.isalnum() or not (3 <= len(text) <= 16):
            bot.send_message(m.chat.id, "❌ Неверный ник.")


            return

        temp[uid] = {"nick": text}
        states[uid] = WAIT_FACTION

        bot.send_message(m.chat.id, "Выберите фракцию:", reply_markup=faction_kb())
        return

    # ─ Faction
    if states[uid] == WAIT_FACTION:
        if text not in ["🔴 Красные", "🔵 Синие"]:
            return

        temp[uid]["faction"] = text
        states[uid] = WAIT_KIT

        bot.send_message(m.chat.id, "Выберите свой kit:", reply_markup=kit_kb())
        return

    # ─ Kit
    if states[uid] == WAIT_KIT:
        temp[uid]["kit"] = text
        states[uid] = WAIT_CONFIRM

        bot.send_message(
            m.chat.id,
            f'{temp[uid]["nick"]}, Вы выбрали фракцию "{temp[uid]["faction"]}" и kit "{temp[uid]["kit"]}".\nВы уверены?',
            reply_markup=confirm_kb()
        )
        return

    # ─ Confirm
    if states[uid] == WAIT_CONFIRM:

        if text == "Выбрать заново ❌":
            states[uid] = WAIT_NICK
            temp.pop(uid, None)
            bot.send_message(m.chat.id, "Введите Minecraft ник:")
            return

        if text == "Да ✅":

            username = m.from_user.username or "unknown"

            user = {
                "telegram_id": uid,
                "telegram_username": username,
                "minecraft_nick": temp[uid]["nick"],
                "faction": temp[uid]["faction"],
                "kit": temp[uid]["kit"]
            }

            add_user(user)

            # 👇 HERE MC WHITELIST
            # add_to_whitelist(user)

            states.pop(uid)
            temp.pop(uid)

            bot.send_message(m.chat.id, "✅ Заявка принята.")
            return


bot.infinity_polling(skip_pending=True)