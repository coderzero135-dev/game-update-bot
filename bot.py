import os, asyncio, time, json
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
import aiohttp

TOKEN = os.getenv("DISCORD_TOKEN", "")
if not TOKEN and os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if line.strip().startswith("DISCORD_TOKEN="):
                TOKEN = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                break

CONFIG_FILE = "bot_config.json"

GAMES = {
    "730": ("CS2", "fps"),
    "1172470": ("Apex Legends", "br"),
    "271590": ("GTA V", "openworld"),
    "1938090": ("Call of Duty", "fps"),
    "578080": ("PUBG", "br"),
    "252490": ("Rust", "survival"),
    "440": ("TF2", "fps"),
    "236390": ("War Thunder", "sim"),
    "230410": ("Warframe", "looter"),
    "359550": ("R6 Siege", "fps"),
    "381210": ("Dead by Daylight", "horror"),
    "594650": ("Hunt: Showdown", "fps"),
    "1623730": ("Palworld", "survival"),
    "2923300": ("FragPunk", "fps"),
    "1693980": ("Deadlock", "moba"),
    "221100": ("DayZ", "survival"),
    "2507950": ("Delta Force", "fps"),
    "252950": ("Rocket League", "sports"),
    "2767030": ("Marvel Rivals", "hero"),
    "1172620": ("Sea of Thieves", "adventure"),
    "393380": ("SQUAD", "fps"),
    "513710": ("Scum", "survival"),
    "872200": ("Rogue Company", "fps"),
    "2479810": ("Gray Zone Warfare", "fps"),
    "760160": ("Bloodhunt", "br"),
    "671860": ("BattleBit", "fps"),
    "761890": ("Albion Online", "mmo"),
    "1067180": ("Stalcraft", "mmo"),
    "2338310": ("The First Descendant", "looter"),
    "2819640": ("ARC Raiders", "survival"),
    "2015270": ("Dark and Darker", "dungeon"),
    "686810": ("Hell Let Loose", "fps"),
    "1874880": ("Arma Reforger", "sim"),
    "107410": ("Arma 3", "sim"),
    "304930": ("Unturned", "survival"),
    "376210": ("The Isle", "survival"),
    "581320": ("Insurgency Sandstorm", "fps"),
    "1144200": ("Ready or Not", "fps"),
    "2406770": ("Bodycam", "fps"),
    "1517290": ("Battlefield 2042", "fps"),
    "1238810": ("Battlefield V", "fps"),
    "1238840": ("Battlefield 1", "fps"),
    "1174180": ("RDR2", "openworld"),
    "945360": ("Among Us", "party"),
    "2221490": ("The Division 2", "looter"),
    "440900": ("Conan Exiles", "survival"),
    "1203220": ("Naraka", "br"),
    "2399830": ("ARK Ascended", "survival"),
    "346110": ("ARK Evolved", "survival"),
    "2357570": ("Overwatch 2", "hero"),
    "2686150": ("The Finals", "fps"),
    "1928420": ("Farlight 84", "br"),
    "895400": ("Deadside", "survival"),
    "2318300": ("Dune Awakening", "mmo"),
    "2873710": ("SMITE 2", "moba"),
    "291480": ("Warface", "fps"),
    "108600": ("Project Zomboid", "survival"),
    "1237950": ("Battlefront II", "fps"),
    "238960": ("Path of Exile", "arpg"),
    "2694490": ("Path of Exile 2", "arpg"),
    "2668510": ("Snowbreak", "gacha"),
    "2358720": ("Black Myth Wukong", "arpg"),
    "1245620": ("ELDEN RING", "arpg"),
    "1086940": ("Baldurs Gate 3", "rpg"),
    "553850": ("HELLDIVERS 2", "horde"),
    "2246340": ("MH Wilds", "arpg"),
    "1145360": ("Hades II", "rogue"),
    "2826790": ("PIONER", "mmo"),
    "2381850": ("Arena Breakout", "fps"),
}

CAT_ICONS = {
    "fps": "\U0001f52b", "br": "\U0001f3af", "survival": "\U0001faa8",
    "mmo": "\U0001f310", "hero": "\U0001f9d1\u200d\U0001f4bb", "moba": "\u2694\ufe0f",
    "arpg": "\U0001f5e1\ufe0f", "openworld": "\U0001f30d", "sim": "\U0001f3cd\ufe0f",
    "horror": "\U0001f47b", "sports": "\u26bd", "looter": "\U0001f4e6",
    "horde": "\U0001f41b", "rogue": "\U0001f3b2", "party": "\U0001f389",
    "rpg": "\U0001f4dc", "dungeon": "\U0001f9d9", "gacha": "\U0001f3b0",
    "adventure": "\u26f5",
}

CACHE = {}
CACHE_TTL = 600
_prefetched = False

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
                params={"appid": appid, "count": 1, "maxlength": 300, "format": "json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status != 200:
                    return None, None, None
                data = await r.json()
                items = data.get("appnews", {}).get("newsitems", [])
                if not items:
                    return None, None, None
                return items[0].get("date", 0), items[0].get("url", ""), items[0].get("title", "")
        except:
            return None, None, None

async def fetch_games():
    now = time.time()
    sem = asyncio.Semaphore(15)
    results = []
    async with aiohttp.ClientSession() as session:
        async def one(appid, name_tag):
            name, tag = name_tag
            ck = f"u_{appid}"
            if ck in CACHE and now - CACHE[ck]["ts"] < CACHE_TTL:
                ts, url, title = CACHE[ck]["data"]
            else:
                ts, url, title = await do_fetch(appid, session, sem)
                CACHE[ck] = {"ts": now, "data": (ts, url, title)}
            results.append({"name": name, "tag": tag, "appid": appid, "ts": ts, "url": url, "title": title})
        await asyncio.gather(*[one(aid, nt) for aid, nt in GAMES.items()])
    return results

def fmt(ts):
    if not ts:
        return "--"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    now_t = datetime.now(timezone.utc)
    diff = now_t - dt
    if diff.days == 0:
        h = diff.seconds // 3600
        m = (diff.seconds % 3600) // 60
        if h:
            return f"{h}h"
        if m:
            return f"{m}m"
        return "now"
    if diff.days == 1:
        return "1d"
    if diff.days < 7:
        return f"{diff.days}d"
    if diff.days < 30:
        return f"{diff.days//7}w"
    if diff.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%b %Y")

def build_board(results):
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)
    now_ts = datetime.now(timezone.utc).timestamp()

    today = [r for r in results if r["ts"] and (now_ts - r["ts"]) < 86400]
    week = [r for r in results if r["ts"] and 86400 <= (now_ts - r["ts"]) < 604800]
    older = [r for r in results if r["ts"] and (now_ts - r["ts"]) >= 604800]
    none = [r for r in results if not r["ts"]]

    def format_list(items, icon):
        if not items:
            return []
        lines = []
        for i, r in enumerate(items):
            cat = CAT_ICONS.get(r["tag"], "")
            lines.append(f"{icon} `{fmt(r['ts']):>5}` {cat} **{r['name']}**")
        return lines

    embeds = []

    recent_lines = format_list(today, "\U0001f7e2") + format_list(week, "\U0001f7e1")
    if recent_lines:
        desc = "\n".join(recent_lines[:60])
        if len(recent_lines) > 60:
            desc += f"\n*...and {len(recent_lines)-60} more*"
        embed = discord.Embed(
            title="Recently Updated",
            description=desc,
            color=0x3fb950,
            timestamp=datetime.now(timezone.utc),
        )
        embeds.append(embed)

    other_lines = format_list(older, "\U0001f534") + format_list(none, "\u26ab")
    if other_lines:
        for i in range(0, len(other_lines), 75):
            chunk = other_lines[i:i+75]
            is_last = i + 75 >= len(other_lines)
            embed = discord.Embed(
                title="All Games" if i == 0 else "",
                description="\n".join(chunk),
                color=0x30363d,
            )
            if is_last:
                embed.set_footer(text=f"{len(results)} games | updates every 10 min")
            embeds.append(embed)

    return embeds if embeds else [discord.Embed(title="No data", description="Fetching...", color=0x30363d)]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands")
    pinned_updater.start()
    asyncio.create_task(prefetch())
    print("Ready.")

async def prefetch():
    print("Prefetching game data...")
    t0 = time.time()
    await fetch_games()
    print(f"Prefetch done in {time.time()-t0:.1f}s")

@bot.tree.command(name="ping", description="Check if bot is online")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

@bot.tree.command(name="updates", description="Show all game updates")
async def updates_cmd(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    try:
        results = await fetch_games()
        if game:
            q = game.lower()
            results = [r for r in results if q in r["name"].lower()]
        if not results:
            await interaction.followup.send("No games found.")
            return
        for embed in build_board(results):
            await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

@bot.tree.command(name="latest", description="Details for a specific game")
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
        embed = discord.Embed(
            title=f"{CAT_ICONS.get(r['tag'],'')} {r['name']}",
            description=f"Last update: **{fmt(r['ts'])}**",
            color=0x1f6feb,
        )
        if r["url"]:
            embed.add_field(name="Link", value=r["url"], inline=False)
        if r["title"]:
            embed.add_field(name="Latest News", value=r["title"][:256], inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

def _score(q, n):
    if q == n: return 100
    if n.startswith(q): return 90
    if q in n: return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))

@bot.tree.command(name="pinboard", description="Create the auto-updating status board")
@commands.has_permissions(manage_messages=True)
async def pinboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        results = await fetch_games()
        embeds = build_board(results)
        msg = await interaction.channel.send(embeds=embeds[:10])
        try:
            await msg.pin()
        except:
            pass
        cfg = load_config()
        cfg["channel_id"] = interaction.channel_id
        cfg["message_id"] = msg.id
        cfg["message_count"] = len(embeds)
        cfg["last_ts"] = {r["appid"]: r["ts"] or 0 for r in results}
        save_config(cfg)
        await interaction.followup.send("Board pinned. Auto-updates every 10 min.")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

@bot.tree.command(name="stopboard", description="Stop the auto-updating board")
@commands.has_permissions(manage_messages=True)
async def stopboard_cmd(interaction: discord.Interaction):
    save_config({})
    await interaction.response.send_message("Stopped.")

@bot.tree.command(name="search", description="Search tracked games")
async def search_cmd(interaction: discord.Interaction, name: str):
    q = name.lower()
    matches = [(n, t) for aid, (n, t) in GAMES.items() if q in n.lower()]
    if not matches:
        await interaction.response.send_message("No matches.")
        return
    lines = [f"{CAT_ICONS.get(t,'')} {n}" for n, t in sorted(matches)[:25]]
    await interaction.response.send_message("**Games:**\n" + "\n".join(lines))

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
            cat = CAT_ICONS.get(r["tag"], "")
            alerts.append(f"{cat} **{r['name']}** updated ({fmt(ts)})")
        last_ts[appid] = ts

    embeds = build_board(results)
    await pinned_msg.edit(embeds=embeds[:10])

    if alerts:
        alert_embed = discord.Embed(
            title="\U0001f514 New Updates",
            description="\n".join(alerts[:20]),
            color=0x3fb950,
        )
        await channel.send(embed=alert_embed, delete_after=600)

    cfg["last_ts"] = last_ts
    save_config(cfg)

@pinned_updater.before_loop
async def _():
    await bot.wait_until_ready()

if __name__ == "__main__":
    if not TOKEN:
        print("No DISCORD_TOKEN found in .env.")
        exit(1)
    print("Starting...")
    bot.run(TOKEN, log_handler=None)
