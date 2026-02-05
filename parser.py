import json
from config import *
from logger import log

class DB:

    def __init__(self, bot):
        self.bot = bot
        self.cache = self.load_local()

    def load_local(self):
        with open("base.jsonc", "r") as f:
            return json.load(f)

    def save_local(self):
        with open("base.jsonc", "w") as f:
            json.dump(self.cache, f, indent=2)

    # ========= TELEGRAM STORAGE =========

    def add_whitelist(self, tg_id, nick):
        text = f"{tg_id}|{nick}"
        self.bot.send_message(DB_GROUP_ID, text, message_thread_id=WHITELIST_TOPIC)

    def add_ban(self, tg_id, nick):
        text = f"{tg_id}|{nick}"
        self.bot.send_message(DB_GROUP_ID, text, message_thread_id=BANLIST_TOPIC)

    def add_profile(self, tg_id, nick, faction, kit):
        text = f"{tg_id}|{nick}|{faction}|{kit}"
        self.bot.send_message(DB_GROUP_ID, text, message_thread_id=PROFILES_TOPIC)

    # ========= FUTURE MINECRAFT =========

    def mc_whitelist(self, nick):
        pass  # RCON

    def mc_ban(self, nick):
        pass

    def mc_assign_team(self, nick, faction):
        pass

    def mc_assign_kit(self, nick, kit):
        pass
