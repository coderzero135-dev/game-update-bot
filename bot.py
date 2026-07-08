import os

TOKEN = os.getenv("DISCORD_TOKEN", "")
for line in open(".env"):
    if line.startswith("DISCORD_TOKEN="):
        TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

import asyncio, time, json
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
import aiohttp

CONFIG_FILE = "bot_config.json"

GAMES = {
    "730": "CS2", "1172470": "Apex Legends", "271590": "GTA V",
    "1938090": "Call of Duty", "578080": "PUBG", "252490": "Rust",
    "440": "TF2", "236390": "War Thunder", "230410": "Warframe",
    "359550": "R6 Siege", "381210": "Dead by Daylight", "594650": "Hunt: Showdown",
    "1623730": "Palworld", "2923300": "FragPunk", "1693980": "Deadlock",
    "221100": "DayZ", "2507950": "Delta Force", "252950": "Rocket League",
    "2767030": "Marvel Rivals", "1172620": "Sea of Thieves", "393380": "SQUAD",
    "513710": "Scum", "872200": "Rogue Company", "2479810": "Gray Zone Warfare",
    "760160": "Bloodhunt", "671860": "BattleBit", "761890": "Albion Online",
    "1067180": "Stalcraft", "2338310": "The First Descendant",
    "2819640": "ARC Raiders", "2015270": "Dark and Darker",
    "686810": "Hell Let Loose", "1874880": "Arma Reforger", "107410": "Arma 3",
    "304930": "Unturned", "376210": "The Isle", "581320": "Insurgency: Sandstorm",
    "1144200": "Ready or Not", "2406770": "Bodycam", "674020": "World War 3",
    "1517290": "Battlefield 2042", "1238810": "Battlefield V", "1238840": "Battlefield 1",
    "1174180": "RDR2", "945360": "Among Us", "2221490": "The Division 2",
    "440900": "Conan Exiles", "1203220": "Naraka", "2399830": "ARK Ascended",
    "346110": "ARK Evolved", "2357570": "Overwatch 2", "2686150": "The Finals",
    "1928420": "Farlight 84", "895400": "Deadside", "2318300": "Dune: Awakening",
    "2873710": "SMITE 2", "291480": "Warface", "108600": "Project Zomboid",
    "1237950": "Battlefront II", "238960": "Path of Exile", "2694490": "Path of Exile 2",
    "2668510": "Snowbreak", "2358720": "Black Myth Wukong", "1245620": "ELDEN RING",
    "1086940": "Baldurs Gate 3", "553850": "HELLDIVERS 2", "2246340": "Monster Hunter Wilds",
    "1145360": "Hades II", "2826790": "PIONER", "2381850": "Arena Breakout",
}

CACHE = {}
CACHE_TTL = 600

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
    except:
        pass

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def do_fetch(appid, session, sem):
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    async with sem:
        try:
            async with session.get(
                url,
                params={"appid": appid, "count": 1, "maxlength": 1, "format": "json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status != 200:
                    return None, None
                data = await r.json()
                items = data.get("appnews", {}).get("newsitems", [])
                if not items:
                    return None, None
                return items[0].get("date", 0), items[0].get("url", "")
        except:
            return None, None

async def fetch_games():
    now = time.time()
    sem = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        async def one(appid, name):
            ck = f"u_{appid}"
            if ck in CACHE and now - CACHE[ck]["ts"] < CACHE_TTL:
                ts, url = CACHE[ck]["data"]
            else:
                ts, url = await do_fetch(appid, session, sem)
                CACHE[ck] = {"ts": now, "data": (ts, url)}
            return {"name": name, "appid": appid, "ts": ts, "url": url}

        coros = [one(aid, name) for aid, name in GAMES.items()]
        return await asyncio.gather(*coros)

def fmt(ts):
    if not ts:
        return "--"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    now_t = datetime.now(timezone.utc)
    diff = now_t - dt
    if diff.days == 0:
        h = diff.seconds // 3600
        m = (diff.seconds % 3600) // 60
        if h: return f"{h}h {m}m ago"
        if m: return f"{m}m ago"
        return "now"
    if diff.days == 1: return "yesterday"
    if diff.days < 7: return f"{diff.days}d ago"
    if diff.days < 30: return f"{diff.days//7}w ago"
    if diff.days < 365: return dt.strftime("%b %d")
    return dt.strftime("%b %Y")

def build_embed(results, title="Game Updates"):
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)
    fields = []
    for r in results:
        ts = r["ts"] or 0
        now_ts = datetime.now(timezone.utc).timestamp()
        if ts == 0: s = "\u26ab"
        elif (now_ts - ts) < 86400: s = "\U0001f7e2"
        elif (now_ts - ts) < 604800: s = "\U0001f7e1"
        else: s = "\U0001f534"
        fields.append((s, r["name"], fmt(r["ts"])))
    chunk_size = (len(fields) + 2) // 3
    cols = [fields[i:i+chunk_size] for i in range(0, len(fields), chunk_size)]

    embed = discord.Embed(title=title, color=0x1f6feb, timestamp=datetime.now(timezone.utc))
    for col in cols:
        text = "\n".join(f"{s} `{w:<11}` **{n}**" for s, n, w in col)
        embed.add_field(name="\u200b", value=text or "\u200b", inline=True)
    embed.set_footer(text=f"Updates every 10 min | {len(results)} games")
    return embed

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands: {[c.name for c in synced]}")
    pinned_updater.start()
    print("Ready.")

@bot.tree.command(name="ping", description="Test bot")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

@bot.tree.command(name="updates", description="Show latest game updates")
async def updates_cmd(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    try:
        print("Fetching...")
        results = await fetch_games()
        print(f"Got {len(results)} results")
        if game:
            q = game.lower()
            results = [r for r in results if q in r["name"].lower()]
        if not results:
            await interaction.followup.send("No updates found.")
            return
        embed = build_embed(results, "Game Updates" + (f' matching "{game}"' if game else ""))
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="latest", description="Show latest update for a game")
async def latest_cmd(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    try:
        results = await fetch_games()
        q = game.lower()
        matches = [(r, s) for r in results if (s := _score(q, r["name"].lower())) > 0]
        matches.sort(key=lambda x: x[1], reverse=True)
        if not matches:
            await interaction.followup.send(f"No game matching `{game}`.")
            return
        r = matches[0][0]
        embed = discord.Embed(title=r["name"], description=f"Last update: **{fmt(r['ts'])}**", color=0x1f6feb)
        if r["url"]:
            embed.add_field(name="Patch Notes", value=r["url"], inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

def _score(q, n):
    if q == n: return 100
    if n.startswith(q): return 90
    if q in n: return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))

@bot.tree.command(name="pinboard", description="Create auto-updating pinned status board")
@commands.has_permissions(manage_messages=True)
async def pinboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        results = await fetch_games()
        embed = build_embed(results, "Game Update Status")
        msg = await interaction.channel.send(embed=embed)
        try:
            await msg.pin()
        except:
            pass
        cfg = load_config()
        cfg["channel_id"] = interaction.channel_id
        cfg["message_id"] = msg.id
        cfg["last_ts"] = {r["appid"]: r["ts"] or 0 for r in results}
        save_config(cfg)
        await interaction.followup.send("Board pinned. Auto-updating every 10 min.")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

@bot.tree.command(name="stopboard", description="Stop the auto-updating board")
@commands.has_permissions(manage_messages=True)
async def stopboard_cmd(interaction: discord.Interaction):
    save_config({"channel_id": 0, "message_id": 0, "last_ts": {}})
    await interaction.response.send_message("Stopped.")

@bot.tree.command(name="search", description="Search tracked games")
async def search_cmd(interaction: discord.Interaction, name: str):
    q = name.lower()
    matches = [n for n in GAMES.values() if q in n.lower()]
    await interaction.response.send_message("**Games:**\n" + "\n".join(f"- {m}" for m in sorted(matches)[:25]) or "No matches.")

@tasks.loop(minutes=10)
async def pinned_updater():
    cfg = load_config()
    cid = cfg.get("channel_id", 0)
    mid = cfg.get("message_id", 0)
    if not cid or not mid:
        return
    channel = bot.get_channel(cid)
    if not channel:
        return
    try:
        pinned_msg = await channel.fetch_message(mid)
    except:
        return
    results = await fetch_games()
    cfg = load_config()
    last_ts = cfg.get("last_ts", {})
    alerts = []
    for r in results:
        appid = r["appid"]
        ts = r["ts"] or 0
        prev = last_ts.get(appid, 0)
        if ts > prev and prev > 0:
            alerts.append(f"**{r['name']}** updated - {fmt(ts)}")
        last_ts[appid] = ts
    embed = build_embed(results, "Game Update Status")
    await pinned_msg.edit(content=None, embed=embed)
    if alerts:
        await channel.send(embed=discord.Embed(title="New Updates", description="\n".join(alerts), color=0x3fb950), delete_after=600)
    cfg["last_ts"] = last_ts
    save_config(cfg)

@pinned_updater.before_loop
async def _():
    await bot.wait_until_ready()

if __name__ == "__main__":
    if not TOKEN:
        print("No DISCORD_TOKEN found in .env or environment.")
        exit(1)
    print("Starting bot...")
    bot.run(TOKEN, log_handler=None)
