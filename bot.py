import os, time, asyncio, json, traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
import aiohttp

TOKEN = os.getenv("DISCORD_TOKEN", "")
CONFIG_FILE = os.getenv("CONFIG_FILE", "bot_config.json")

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
    "1067180": "Stalcraft", "2338310": "The First Descendant", "2826790": "PIONER",
    "2819640": "ARC Raiders", "2381850": "Arena Breakout", "2015270": "Dark and Darker",
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
    "1086940": "Baldur's Gate 3", "553850": "HELLDIVERS 2", "2246340": "Monster Hunter Wilds",
    "1145360": "Hades II",
}

CACHE = {}
CACHE_TTL = 600

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
    except Exception:
        pass

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
_session = None
_sem = None

def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

def get_sem():
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(10)
    return _sem

async def fetch_latest(appid):
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    try:
        async with get_sem():
            async with get_session().get(
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
    except Exception:
        return None, None

async def fetch_all():
    now = time.time()
    results = []

    async def one(appid, name):
        ck = f"u_{appid}"
        if ck in CACHE and now - CACHE[ck]["ts"] < CACHE_TTL:
            ts, url = CACHE[ck]["data"]
        else:
            ts, url = await fetch_latest(appid)
            CACHE[ck] = {"ts": now, "data": (ts, url)}
        results.append({"name": name, "appid": appid, "ts": ts, "url": url})

    coros = [one(aid, name) for aid, name in GAMES.items()]
    try:
        await asyncio.wait_for(asyncio.gather(*coros), timeout=30)
    except asyncio.TimeoutError:
        pass
    return results

def fmt(ts):
    if not ts:
        return "—"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    now_t = datetime.now(timezone.utc)
    diff = now_t - dt
    if diff.days == 0:
        h = diff.seconds // 3600
        m = (diff.seconds % 3600) // 60
        if h:
            return f"{h}h {m}m ago"
        if m:
            return f"{m}m ago"
        return "now"
    if diff.days == 1:
        return "yesterday"
    if diff.days < 7:
        return f"{diff.days}d ago"
    if diff.days < 30:
        return f"{diff.days // 7}w ago"
    if diff.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%b %Y")

def build_embed(results, title="Game Updates"):
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)

    emojis = {"today": "🟢", "recent": "🟡", "old": "🔴", "none": "⚫"}

    fields = []
    for r in results:
        ts = r["ts"] or 0
        now_ts = datetime.now(timezone.utc).timestamp()
        if ts == 0:
            status = emojis["none"]
        elif (now_ts - ts) < 86400:
            status = emojis["today"]
        elif (now_ts - ts) < 604800:
            status = emojis["recent"]
        else:
            status = emojis["old"]
        fields.append((status, r["name"], fmt(r["ts"])))

    mid = (len(fields) + 1) // 2
    left = fields[:mid]
    right = fields[mid:]

    left_str = "\n".join(f"{s} `{w:<11}` **{n}**" for s, n, w in left)
    right_str = "\n".join(f"{s} `{w:<11}` **{n}**" for s, n, w in right)

    embed = discord.Embed(title=title, color=0x1f6feb, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="\u200b", value=left_str or "\u200b", inline=True)
    embed.add_field(name="\u200b", value=right_str or "\u200b", inline=True)
    embed.set_footer(text=f"Updates every 10 min | {len(results)} games | 🟢 <1d  🟡 <1w  🔴 older  ⚫ none")
    return embed

# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
        for cmd in synced:
            print(f"  /{cmd.name}")
    except Exception as e:
        print(f"Sync error: {e}")
        traceback.print_exc()
    pinned_updater.start()

# ---------- Commands ----------
@bot.tree.command(name="ping", description="Check if bot is alive and API works")
async def cmd_ping(interaction: discord.Interaction):
    await interaction.response.defer()
    t0 = time.time()
    results = await fetch_all()
    ok = sum(1 for r in results if r["ts"])
    elapsed = time.time() - t0
    await interaction.followup.send(f"Online. {ok}/{len(results)} games fetched in {elapsed:.1f}s. Use `/pinboard` to create the status board.")

@bot.tree.command(name="updates", description="Show latest game updates")
async def cmd_updates(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    results = await fetch_all()
    if game:
        q = game.lower()
        results = [r for r in results if q in r["name"].lower()]
    if not results:
        await interaction.followup.send("No updates found.")
        return
    title = "Game Updates"
    if game:
        title += f' matching "{game}"'
    embed = build_embed(results, title)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="latest", description="Show latest update for a specific game")
async def cmd_latest(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    results = await fetch_all()
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

def _score(q, n):
    if q == n: return 100
    if n.startswith(q): return 90
    if q in n: return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))

@bot.tree.command(name="pinboard", description="Create/refresh the auto-updating pinned status board")
@commands.has_permissions(manage_messages=True)
async def cmd_pinboard(interaction: discord.Interaction):
    await interaction.response.defer()
    results = await fetch_all()
    embed = build_embed(results, "Game Update Status")
    msg = await interaction.channel.send(embed=embed)
    try:
        await msg.pin()
    except Exception:
        pass
    cfg = load_config()
    cfg["channel_id"] = interaction.channel_id
    cfg["message_id"] = msg.id
    cfg["last_ts"] = {r["appid"]: r["ts"] or 0 for r in results}
    save_config(cfg)
    await interaction.followup.send("Board pinned. Auto-updating every 10 min.")

@bot.tree.command(name="stopboard", description="Stop the auto-updating board")
@commands.has_permissions(manage_messages=True)
async def cmd_stopboard(interaction: discord.Interaction):
    cfg = load_config()
    cfg["channel_id"] = 0
    cfg["message_id"] = 0
    save_config(cfg)
    await interaction.response.send_message("Auto-update board stopped.")

@bot.tree.command(name="search", description="Search tracked games")
async def cmd_search(interaction: discord.Interaction, name: str):
    q = name.lower()
    matches = [n for n in GAMES.values() if q in n.lower()]
    if not matches:
        await interaction.response.send_message("No matches.")
        return
    await interaction.response.send_message("**Games:**\n" + "\n".join(f"• {m}" for m in sorted(matches)[:25]))

# ---------- Background pinned-updater ----------
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
    except Exception:
        return
    results = await fetch_all()
    cfg = load_config()
    last_ts = cfg.get("last_ts", {})
    alerts = []
    for r in results:
        appid = r["appid"]
        ts = r["ts"] or 0
        prev = last_ts.get(appid, 0)
        if ts > prev and prev > 0:
            alerts.append(f"**{r['name']}** updated — {fmt(ts)}")
        last_ts[appid] = ts
    embed = build_embed(results, "Game Update Status")
    await pinned_msg.edit(content=None, embed=embed)
    if alerts:
        await channel.send(embed=discord.Embed(title="New Updates Detected", description="\n".join(alerts), color=0x3fb950), delete_after=600)
    cfg["last_ts"] = last_ts
    save_config(cfg)

@pinned_updater.before_loop
async def before_pinned():
    await bot.wait_until_ready()

# ---------- Run ----------
MAX_RETRIES = 5
RETRY_DELAY = 30

def run_bot():
    retries = 0
    while True:
        try:
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure:
            print("Invalid token. Exiting.")
            break
        except Exception as e:
            retries += 1
            print(f"Connection lost ({e}). Retry {retries}/{MAX_RETRIES} in {RETRY_DELAY}s...")
            if retries >= MAX_RETRIES:
                print("Max retries. Exiting.")
                break
            time.sleep(RETRY_DELAY)
        else:
            break

if __name__ == "__main__":
    if not TOKEN:
        tok = os.getenv("DISCORD_TOKEN", "")
        if tok:
            TOKEN = tok
    if not TOKEN:
        print("Paste your Discord bot token:")
        TOKEN = input("> ").strip()
        if not TOKEN:
            print("No token provided.")
            exit(1)

    PORT = int(os.getenv("PORT", "8080"))

    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        def log_message(self, *a):
            pass

    import threading
    httpd = HTTPServer(("0.0.0.0", PORT), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"Health server on port {PORT}")

    print("Starting bot...")
    run_bot()
