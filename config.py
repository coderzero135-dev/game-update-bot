"""Game Update Bot - Configuration"""

import os
import json
import logging

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Discord ---
TOKEN = os.getenv("DISCORD_TOKEN", "")
if not TOKEN:
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("DISCORD_TOKEN="):
                    TOKEN = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break

# --- Timing ---
STEAM_CACHE_TTL = 120       # Steam RSS: 2 min
EXTERNAL_CACHE_TTL = 600    # Google News, Reddit, RSS: 10 min
BUILD_CHECK_TTL = 120       # Build version check: 2 min
BOARD_UPDATE_INTERVAL = 2   # Board refresh: 2 min

# --- Sources ---
STEAM_SEMAPHORE = 20
EXTERNAL_SEMAPHORE = 10
REQUEST_TIMEOUT = 6

# --- Database ---
DB_PATH = os.path.join(DATA_DIR, "gamebot.db")

# --- Web Dashboard ---
WEB_PORT = int(os.getenv("PORT", "8080"))
WEB_HOST = "0.0.0.0"

# --- Logging ---
LOG_LEVEL = logging.INFO
LOG_FILE = os.path.join(DATA_DIR, "bot.log")


# --- Games ---
def load_games():
    """Load games from config file or use built-in defaults."""
    games_file = os.path.join(DATA_DIR, "games.json")
    if os.path.exists(games_file):
        try:
            with open(games_file) as f:
                return json.load(f)
        except Exception:
            pass

    # Default game list
    return {
        "steam": {
            "730": "CS2",
            "1172470": "Apex Legends",
            "271590": "GTA V",
            "1938090": "Call of Duty",
            "578080": "PUBG",
            "252490": "Rust",
            "440": "TF2",
            "236390": "War Thunder",
            "230410": "Warframe",
            "359550": "R6 Siege",
            "381210": "Dead by Daylight",
            "594650": "Hunt: Showdown",
            "1623730": "Palworld",
            "2923300": "FragPunk",
            "1693980": "Deadlock",
            "221100": "DayZ",
            "2507950": "Delta Force",
            "252950": "Rocket League",
            "2767030": "Marvel Rivals",
            "1172620": "Sea of Thieves",
            "393380": "SQUAD",
            "513710": "Scum",
            "2479810": "Gray Zone Warfare",
            "671860": "BattleBit",
            "761890": "Albion Online",
            "1067180": "Stalcraft",
            "2338310": "The First Descendant",
            "2819640": "ARC Raiders",
            "2015270": "Dark and Darker",
            "686810": "Hell Let Loose",
            "1874880": "Arma Reforger",
            "107410": "Arma 3",
            "304930": "Unturned",
            "376210": "The Isle",
            "581320": "Insurgency Sandstorm",
            "1144200": "Ready or Not",
            "2406770": "Bodycam",
            "1517290": "Battlefield 2042",
            "1238810": "Battlefield V",
            "1238840": "Battlefield 1",
            "1174180": "RDR2",
            "945360": "Among Us",
            "2221490": "The Division 2",
            "440900": "Conan Exiles",
            "1203220": "Naraka",
            "2399830": "ARK Ascended",
            "346110": "ARK Evolved",
            "2357570": "Overwatch 2",
            "2686150": "The Finals",
            "895400": "Deadside",
            "2318300": "Dune Awakening",
            "2873710": "SMITE 2",
            "291480": "Warface",
            "108600": "Project Zomboid",
            "1237950": "Battlefront II",
            "238960": "Path of Exile",
            "2694490": "Path of Exile 2",
            "2668510": "Snowbreak",
            "2358720": "Black Myth Wukong",
            "1245620": "ELDEN RING",
            "1086940": "Baldurs Gate 3",
            "553850": "HELLDIVERS 2",
            "2246340": "MH Wilds",
            "1145360": "Hades II",
            "2826790": "PIONER",
            "2381850": "Arena Breakout",
        },
        "non_steam": {
            "valorant": "Valorant",
            "fortnite": "Fortnite",
            "tarkov": "Tarkov",
            "genshin": "Genshin Impact",
            "starrail": "Honkai Star Rail",
            "wuwa": "Wuthering Waves",
            "zzz": "Zenless Zone Zero",
            "minecraft": "Minecraft",
            "roblox": "Roblox",
            "osu": "osu!",
            "lol": "LoL",
            "fivem": "FiveM",
            "chess": "Chess",
        },
    }
