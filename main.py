import telebot
from telebot import types
from config import *
from flask import keep_alive
from parser import DB
from logger import log

bot = telebot.TeleBot(BOT_TOKEN)
db = DB(bot)

keep_alive()

@bot.message_handler(commands=["start"])
def start(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬇ Скачать сборку", url=MODPACK_URL))
    kb.add(types.InlineKeyboardButton("Начать регистрацию", callback_data="reg"))

    bot.send_message(m.chat.id, "Добро пожаловать.", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "reg")
def register(call):
    msg = bot.send_message(call.message.chat.id, "Введи ник Minecraft:")
    bot.register_next_step_handler(msg, get_nick)

def get_nick(m):
    nick = m.text.strip()
    bot.send_message(m.chat.id, "Выбери фракцию: RED / BLUE")
    bot.register_next_step_handler(m, lambda x: get_faction(x, nick))

def get_faction(m, nick):
    faction = m.text.upper()
    bot.send_message(m.chat.id, "Выбери kit:")
    bot.register_next_step_handler(m, lambda x: get_kit(x, nick, faction))

def get_kit(m, nick, faction):
    kit = m.text.upper()
    tg_id = m.from_user.id

    db.add_profile(tg_id, nick, faction, kit)
    db.add_whitelist(tg_id, nick)

    # future minecraft hooks
    # db.mc_whitelist(nick)
    # db.mc_assign_team(nick, faction)
    # db.mc_assign_kit(nick, kit)

    bot.send_message(m.chat.id, "Готово. Ты зарегистрирован.")
    log(f"REGISTER {tg_id} {nick}")

bot.infinity_polling()
