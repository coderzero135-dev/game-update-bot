import os, asyncio, time, json, re
from datetime import datetime, timezone
from xml.etree import ElementTree

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

STEAM = {
    "730": ("CS2", "counter strike 2"),
    "1172470": ("Apex Legends", "apex legends"),
    "271590": ("GTA V", "gta 5"),
    "1938090": ("Call of Duty", "call of duty"),
    "578080": ("PUBG", "pubg battlegrounds"),
    "252490": ("Rust", "rust game"),
    "440": ("TF2", "team fortress 2"),
    "236390": ("War Thunder", "war thunder"),
    "230410": ("Warframe", "warframe"),
    "359550": ("R6 Siege", "rainbow six siege"),
    "381210": ("Dead by Daylight", "dead by daylight"),
    "594650": ("Hunt: Showdown", "hunt showdown"),
    "1623730": ("Palworld", "palworld"),
    "2923300": ("FragPunk", "fragpunk"),
    "1693980": ("Deadlock", "deadlock game"),
    "221100": ("DayZ", "dayz"),
    "2507950": ("Delta Force", "delta force game"),
    "252950": ("Rocket League", "rocket league"),
    "2767030": ("Marvel Rivals", "marvel rivals"),
    "1172620": ("Sea of Thieves", "sea of thieves"),
    "393380": ("SQUAD", "squad game"),
    "513710": ("Scum", "scum game"),
    "872200": ("Rogue Company", "rogue company"),
    "2479810": ("Gray Zone Warfare", "gray zone warfare"),
    "671860": ("BattleBit", "battlebit remastered"),
    "761890": ("Albion Online", "albion online"),
    "1067180": ("Stalcraft", "stalcraft"),
    "2338310": ("The First Descendant", "the first descendant"),
    "2819640": ("ARC Raiders", "arc raiders"),
    "2015270": ("Dark and Darker", "dark and darker"),
    "686810": ("Hell Let Loose", "hell let loose"),
    "1874880": ("Arma Reforger", "arma reforger"),
    "107410": ("Arma 3", "arma 3"),
    "304930": ("Unturned", "unturned"),
    "376210": ("The Isle", "the isle game"),
    "581320": ("Insurgency Sandstorm", "insurgency sandstorm"),
    "1144200": ("Ready or Not", "ready or not game"),
    "2406770": ("Bodycam", "bodycam game"),
    "1517290": ("Battlefield 2042", "battlefield 2042"),
    "1238810": ("Battlefield V", "battlefield 5"),
    "1238840": ("Battlefield 1", "battlefield 1"),
    "1174180": ("RDR2", "red dead redemption 2"),
    "945360": ("Among Us", "among us"),
    "2221490": ("The Division 2", "the division 2"),
    "440900": ("Conan Exiles", "conan exiles"),
    "1203220": ("Naraka", "naraka bladepoint"),
    "2399830": ("ARK Ascended", "ark survival ascended"),
    "346110": ("ARK Evolved", "ark survival evolved"),
    "2357570": ("Overwatch 2", "overwatch 2"),
    "2686150": ("The Finals", "the finals game"),
    "1928420": ("Farlight 84", "farlight 84"),
    "895400": ("Deadside", "deadside"),
    "2318300": ("Dune Awakening", "dune awakening"),
    "2873710": ("SMITE 2", "smite 2"),
    "291480": ("Warface", "warface"),
    "108600": ("Project Zomboid", "project zomboid"),
    "1237950": ("Battlefront II", "star wars battlefront 2"),
    "238960": ("Path of Exile", "path of exile"),
    "2694490": ("Path of Exile 2", "path of exile 2"),
    "2668510": ("Snowbreak", "snowbreak containment zone"),
    "2358720": ("Black Myth Wukong", "black myth wukong"),
    "1245620": ("ELDEN RING", "elden ring"),
    "1086940": ("Baldurs Gate 3", "baldurs gate 3"),
    "553850": ("HELLDIVERS 2", "helldivers 2"),
    "2246340": ("MH Wilds", "monster hunter wilds"),
    "1145360": ("Hades II", "hades 2"),
    "2826790": ("PIONER", "pioner game"),
    "2381850": ("Arena Breakout", "arena breakout infinite"),
}

NON_STEAM = {
    "valorant": ("Valorant", "valorant", "VALORANT"),
    "fortnite": ("Fortnite", "fortnite", "FortNiteBR"),
    "tarkov": ("Tarkov", "escape from tarkov", "EscapefromTarkov"),
    "genshin": ("Genshin Impact", "genshin impact", "Genshin_Impact"),
    "starrail": ("Honkai Star Rail", "honkai star rail", "HonkaiStarRail"),
    "wuwa": ("Wuthering Waves", "wuthering waves", "WutheringWaves"),
    "zzz": ("Zenless Zone Zero", "zenless zone zero", "ZZZ_Official"),
    "minecraft": ("Minecraft", "minecraft", "Minecraft"),
    "roblox": ("Roblox", "roblox", "roblox"),
    "osu": ("osu!", "osu game", "osugame"),
    "lol": ("LoL", "league of legends", "leagueoflegends"),
    "fivem": ("FiveM", "fivem", "FiveM"),
    "chess": ("Chess", "chess game", "chess"),
}

CAT_ICONS = {
    "fps": "\U0001f52b", "br": "\U0001f3af", "survival": "\U0001faa8",
    "mmo": "\U0001f310", "hero": "\U0001f9d1\u200d\U0001f4bb", "moba": "\u2694\ufe0f",
    "arpg": "\U0001f5e1\ufe0f", "openworld": "\U0001f30d", "sim": "\U0001f3cd\ufe0f",
    "horror": "\U0001f47b", "sports": "\u26bd", "looter": "\U0001f4e6",
    "horde": "\U0001f41b", "rogue": "\U0001f3b2", "party": "\U0001f389",
    "rpg": "\U0001f4dc", "dungeon": "\U0001f9d9", "gacha": "\U0001f3b0",
    "adventure": "\u26f5",
    "other": "\U0001f3ae",
}

GAME_TAGS = {}
for d in [STEAM, NON_STEAM]:
    for k, v in d.items():
        name = v[0]
        if "fps" in name.lower() or "call of duty" in name.lower() or "battlefield" in name.lower() or "counter" in name.lower(): t = "fps"
        elif "br" in name.lower() or "apex" in name.lower() or "pubg" in name.lower() or "fortnite" in name.lower() or "valorant" in name.lower(): t = "br"
        elif "survival" in name.lower() or "rust" in name.lower() or "dayz" in name.lower() or "ark" in name.lower(): t = "survival"
        elif "mmo" in name.lower() or "albion" in name.lower() or "stalcraft" in name.lower(): t = "mmo"
        elif "moba" in name.lower() or "deadlock" in name.lower() or "smite" in name.lower() or "lol" in name.lower(): t = "moba"
        elif "arpg" in name.lower() or "path of exile" in name.lower() or "elden ring" in name.lower() or "wukong" in name.lower(): t = "arpg"
        elif "gacha" in name.lower() or "genshin" in name.lower() or "star rail" in name.lower() or "wuwa" in name.lower() or "zzz" in name.lower(): t = "gacha"
        elif "hero" in name.lower() or "overwatch" in name.lower() or "marvel" in name.lower(): t = "hero"
        elif "horror" in name.lower() or "dead by" in name.lower(): t = "horror"
        elif "sports" in name.lower() or "rocket" in name.lower(): t = "sports"
        elif "sim" in name.lower() or "war thunder" in name.lower() or "arma" in name.lower(): t = "sim"
        elif "openworld" in name.lower() or "gta" in name.lower() or "rdr" in name.lower(): t = "openworld"
        elif "looter" in name.lower() or "warframe" in name.lower() or "division" in name.lower(): t = "looter"
        elif "dungeon" in name.lower() or "dark and darker" in name.lower(): t = "dungeon"
        elif "party" in name.lower() or "among" in name.lower() or "roblox" in name.lower(): t = "party"
        elif "rogue" in name.lower() or "hades" in name.lower(): t = "rogue"
        elif "rpg" in name.lower() or "baldur" in name.lower(): t = "rpg"
        elif "adventure" in name.lower() or "sea of" in name.lower(): t = "adventure"
        elif "horde" in name.lower() or "helldiver" in name.lower(): t = "horde"
        else: t = "other"
        GAME_TAGS[name] = t

CACHE = {}
STEAM_TTL = 120
EXTERNAL_TTL = 600
RSS_CACHE = {"data": None, "ts": 0}
_last_fetch_time = 0

def load_config():
    try: return json.load(open(CONFIG_FILE))
    except: return {}

def save_config(cfg):
    try: json.dump(cfg, open(CONFIG_FILE, "w"))
    except: pass

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Sources ---

async def src_steam(appid, session, sem):
    async with sem:
        try:
            async with session.get(
                "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/",
                params={"appid": appid, "count": 1, "maxlength": 300, "format": "json"},
                timeout=aiohttp.ClientTimeout(total=4),
            ) as r:
                if r.status == 200:
                    items = (await r.json()).get("appnews", {}).get("newsitems", [])
                    if items:
                        return items[0].get("date", 0), items[0].get("url", ""), items[0].get("title", ""), "Steam"
        except: pass
    return 0, "", "", "—"

async def src_reddit(subreddit, session, sem):
    async with sem:
        try:
            headers = {"User-Agent": "GameUpdateBot/1.0"}
            async with session.get(
                f"https://www.reddit.com/r/{subreddit}/search.json",
                params={"q": "patch OR update", "sort": "new", "restrict_sr": "on", "limit": 3, "t": "month"},
                headers=headers, timeout=aiohttp.ClientTimeout(total=6),
            ) as r:
                if r.status == 200:
                    posts = (await r.json()).get("data", {}).get("children", [])
                    if posts:
                        p = posts[0]["data"]
                        return p.get("created_utc", 0), f"https://reddit.com{p.get('permalink','')}", p.get("title",""), "Reddit"
        except: pass
    return 0, "", "", "—"

async def src_googlenews(query, session, sem):
    async with sem:
        try:
            q = query.replace(" ", "+")
            async with session.get(
                f"https://news.google.com/rss/search?q={q}+patch+update&hl=en-US&gl=US&ceid=US:en",
                timeout=aiohttp.ClientTimeout(total=6),
            ) as r:
                if r.status == 200:
                    root = ElementTree.fromstring(await r.text())
                    for item in root.iter("item"):
                        title = item.find("title")
                        link = item.find("link")
                        pub = item.find("pubDate")
                        if title is not None and pub is not None:
                            try:
                                dt = datetime.strptime(pub.text or "", "%a, %d %b %Y %H:%M:%S %Z")
                                return dt.replace(tzinfo=timezone.utc).timestamp(), (link.text or ""), (title.text or ""), "Web"
                            except: continue
        except: pass
    return 0, "", "", "—"

async def src_rss_feeds(session):
    now_t = time.time()
    if RSS_CACHE["data"] is not None and now_t - RSS_CACHE["ts"] < EXTERNAL_TTL:
        return RSS_CACHE["data"]

    feeds = [
        "https://www.pcgamer.com/rss/",
        "https://feeds.feedburner.com/ign/all",
        "https://www.eurogamer.net/feed",
    ]
    results = []
    sem = asyncio.Semaphore(3)

    async def fetch_feed(url):
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if r.status != 200: return
                    root = ElementTree.fromstring(await r.text())
                    for item in root.iter("item"):
                        title = item.find("title")
                        link = item.find("link")
                        pub = item.find("pubDate")
                        if title is None or pub is None: continue
                        ttext = (title.text or "").lower()
                        for gid in ALL_GAME_NAMES:
                            if ALL_GAME_NAMES[gid] in ttext:
                                try:
                                    for fmt_str in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S +0000"]:
                                        try:
                                            dt = datetime.strptime(pub.text or "", fmt_str)
                                            break
                                        except: continue
                                    else: continue
                                    results.append((gid, dt.timestamp(), link.text or "", title.text or "", "RSS"))
                                except: pass
            except: pass

    await asyncio.gather(*[fetch_feed(u) for u in feeds])
    RSS_CACHE["data"] = results
    RSS_CACHE["ts"] = now_t
    return results

ALL_GAME_NAMES = {}
for appid, (name, query) in STEAM.items():
    ALL_GAME_NAMES[appid] = name.lower()
for key, (name, query, sub) in NON_STEAM.items():
    ALL_GAME_NAMES[key] = name.lower()

# --- Fetch ---

async def fetch_all():
    global _last_fetch_time
    now_t = time.time()
    sem = asyncio.Semaphore(20)
    results = []
    lock = asyncio.Lock()

    async with aiohttp.ClientSession() as session:
        rss_matches = await src_rss_feeds(session)

        async def fetch_game(gid, name, tag, steam_id=None, reddit_sub=None, google_q=None):
            ck = f"g_{gid}"
            cached = CACHE.get(ck)
            if cached and now_t - cached["ts"] < STEAM_TTL:
                async with lock: results.append(cached["data"])
                return

            s = [src_steam(steam_id, session, sem)] if steam_id else []
            r = [src_reddit(reddit_sub, session, sem)] if reddit_sub else []
            g = [src_googlenews(google_q or name, session, sem)]
            all_s = await asyncio.gather(*(s + r + g))

            best_ts, best_url, best_title, best_src = 0, "", "", "—"
            for ts, url, title, src in all_s:
                if ts > best_ts:
                    best_ts, best_url, best_title, best_src = ts, url, title, src

            for rid, rts, rurl, rtitle, rsrc in rss_matches:
                if rid == gid and rts > best_ts:
                    best_ts, best_url, best_title, best_src = rts, rurl, rtitle, rsrc

            # On subsequent fast ticks, reuse external source data from cache
            if cached and now_t - cached["ts"] < EXTERNAL_TTL and best_src in ("Steam", "—"):
                old = cached["data"]
                if old["src"] not in ("Steam", "—") and old["ts"] > best_ts:
                    best_ts, best_url, best_title, best_src = old["ts"], old["url"], old["title"], old["src"]

            entry = {"id": gid, "name": name, "tag": tag, "ts": best_ts or 0, "url": best_url, "title": best_title, "src": best_src}
            async with lock:
                CACHE[ck] = {"ts": now_t, "data": entry}
                results.append(entry)

        coros = []
        for appid, (name, query) in STEAM.items():
            tag = GAME_TAGS.get(name, "fps")
            coros.append(fetch_game(appid, name, tag, steam_id=appid, google_q=query))
        for key, (name, query, sub) in NON_STEAM.items():
            tag = GAME_TAGS.get(name, "fps")
            coros.append(fetch_game(key, name, tag, reddit_sub=sub, google_q=query))

        await asyncio.gather(*coros)

    _last_fetch_time = time.time()
    return list({r["id"]: r for r in results}.values())

def fmt(ts):
    if not ts: return "--"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    if diff.days == 0:
        h = diff.seconds // 3600; m = (diff.seconds % 3600) // 60
        if h: return f"{h}h"
        if m: return f"{m}m"
        return "now"
    if diff.days == 1: return "1d"
    if diff.days < 7: return f"{diff.days}d"
    if diff.days < 30: return f"{diff.days//7}w"
    if diff.days < 365: return dt.strftime("%b %d")
    return dt.strftime("%b %Y")

def rel_time(ts):
    """Relative time in seconds for 'updated Xs ago'"""
    if not ts: return "?"
    secs = int(time.time() - ts)
    if secs < 60: return f"{secs}s ago"
    if secs < 3600: return f"{secs//60}m ago"
    return f"{secs//3600}h ago"

SRC_ICONS = {"Steam": "\U0001f3ae", "Reddit": "\U0001f4ac", "Web": "\U0001f310", "RSS": "\U0001f4f0", "—": ""}

def build_board(results):
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)
    now_ts = datetime.now(timezone.utc).timestamp()

    today = [r for r in results if r["ts"] and (now_ts - r["ts"]) < 86400]
    week = [r for r in results if r["ts"] and 86400 <= (now_ts - r["ts"]) < 604800]
    older = [r for r in results if r["ts"] and (now_ts - r["ts"]) >= 604800]
    none = [r for r in results if not r["ts"]]

    def fmt_list(items, icon):
        lines = []
        for r in items:
            cat = CAT_ICONS.get(r["tag"], "")
            si = SRC_ICONS.get(r.get("src", ""), "")
            lines.append(f"{icon} `{fmt(r['ts']):>5}` {cat} **{r['name']}** {si}")
        return lines

    embeds = []
    recent = fmt_list(today, "\U0001f7e2") + fmt_list(week, "\U0001f7e1")
    if recent:
        desc = "\n".join(recent[:60])
        if len(recent) > 60:
            desc += f"\n*...and {len(recent)-60} more*"
        embeds.append(discord.Embed(title="Recently Updated", description=desc, color=0x3fb950, timestamp=datetime.now(timezone.utc)))

    rest = fmt_list(older, "\U0001f534") + fmt_list(none, "\u26ab")
    if rest:
        for i in range(0, len(rest), 75):
            chunk = rest[i:i+75]
            embed = discord.Embed(title="All Games" if i == 0 else "", description="\n".join(chunk), color=0x30363d)
            if i + 75 >= len(rest):
                ago = rel_time(_last_fetch_time) if _last_fetch_time else "?"
                embed.set_footer(text=f"{len(results)} games | checked {ago} | \U0001f3ae=Steam \U0001f4ac=Reddit \U0001f310=Web \U0001f4f0=RSS")
            embeds.append(embed)

    return embeds or [discord.Embed(title="No data", description="Fetching...", color=0x30363d)]

# --- Bot ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands")
    pinned_updater.start()
    asyncio.create_task(prefetch())
    print("Ready. Board updates every 2 min.")

async def prefetch():
    print("Prefetching all sources...")
    t0 = time.time()
    r = await fetch_all()
    ok = sum(1 for x in r if x["ts"])
    print(f"Prefetch: {ok}/{len(r)} games in {time.time()-t0:.1f}s")

@bot.tree.command(name="ping", description="Check bot status")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

@bot.tree.command(name="updates", description="Show all game updates")
async def updates_cmd(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    try:
        results = await fetch_all()
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

@bot.tree.command(name="latest", description="Full details for a game")
async def latest_cmd(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    try:
        results = await fetch_all()
        q = game.lower()
        matches = [(r, s) for r in results if (s := _score(q, r["name"].lower())) > 0]
        matches.sort(key=lambda x: x[1], reverse=True)
        if not matches:
            await interaction.followup.send(f"No game matching `{game}`.")
            return
        r = matches[0][0]
        si = SRC_ICONS.get(r.get("src", ""), "")
        embed = discord.Embed(
            title=f"{CAT_ICONS.get(r['tag'],'')} {r['name']}",
            description=f"Source: {r.get('src','?')} {si}\nLast update: **{fmt(r['ts'])}**",
            color=0x1f6feb,
        )
        if r["url"]: embed.add_field(name="Link", value=r["url"], inline=False)
        if r["title"]: embed.add_field(name="Latest", value=r["title"][:256], inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

def _score(q, n):
    if q == n: return 100
    if n.startswith(q): return 90
    if q in n: return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))

@bot.tree.command(name="pinboard", description="Create auto-updating status board (2 min refresh)")
@commands.has_permissions(manage_messages=True)
async def pinboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        results = await fetch_all()
        embeds = build_board(results)
        msg = await interaction.channel.send(embeds=embeds[:10])
        try: await msg.pin()
        except: pass
        cfg = load_config()
        cfg["channel_id"] = interaction.channel_id
        cfg["message_id"] = msg.id
        cfg["last_ts"] = {r["id"]: r["ts"] or 0 for r in results}
        save_config(cfg)
        await interaction.followup.send("Board pinned. Refreshes every **2 minutes**.")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
        import traceback; traceback.print_exc()

@bot.tree.command(name="stopboard", description="Stop the auto-updating board")
@commands.has_permissions(manage_messages=True)
async def stopboard_cmd(interaction: discord.Interaction):
    save_config({})
    await interaction.response.send_message("Stopped.")

@bot.tree.command(name="search", description="Search all tracked games")
async def search_cmd(interaction: discord.Interaction, name: str):
    q = name.lower()
    matches = []
    for appid, (n, _) in STEAM.items():
        if q in n.lower(): matches.append((n, "Steam", GAME_TAGS.get(n, "")))
    for key, (n, _, _) in NON_STEAM.items():
        if q in n.lower(): matches.append((n, "Non-Steam", GAME_TAGS.get(n, "")))
    if not matches:
        await interaction.response.send_message("No matches.")
        return
    lines = [f"{CAT_ICONS.get(t,'')} {n} ({src})" for n, src, t in sorted(matches)[:25]]
    await interaction.response.send_message("**Games:**\n" + "\n".join(lines))

@bot.tree.command(name="refresh", description="Clear cache and re-fetch all sources")
async def refresh_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    CACHE.clear()
    RSS_CACHE["data"] = None
    results = await fetch_all()
    ok = sum(1 for r in results if r["ts"])
    await interaction.followup.send(f"Cleared. Fetched {ok}/{len(results)} games fresh from all sources.")

# --- Background updater (2 min) ---

@tasks.loop(minutes=2)
async def pinned_updater():
    cfg = load_config()
    cid = cfg.get("channel_id", 0)
    mid = cfg.get("message_id", 0)
    if not cid or not mid: return
    channel = bot.get_channel(cid)
    if not channel: return
    try: pinned_msg = await channel.fetch_message(mid)
    except: return

    results = await fetch_all()
    cfg = load_config()
    last_ts = cfg.get("last_ts", {})

    alerts = []
    for r in results:
        rid = r["id"]; ts = r["ts"] or 0
        prev = last_ts.get(rid, 0)
        if ts > prev and prev > 0:
            si = SRC_ICONS.get(r.get("src",""),"")
            alerts.append(f"{CAT_ICONS.get(r['tag'],'')} **{r['name']}** updated ({fmt(ts)}) via {r.get('src','?')} {si}")
        last_ts[rid] = ts

    embeds = build_board(results)
    try: await pinned_msg.edit(embeds=embeds[:10])
    except Exception as e: print(f"Edit error: {e}")

    if alerts:
        await channel.send(embed=discord.Embed(title="\U0001f514 New Updates", description="\n".join(alerts[:20]), color=0x3fb950), delete_after=300)

    cfg["last_ts"] = last_ts
    save_config(cfg)

@pinned_updater.before_loop
async def _(): await bot.wait_until_ready()

if __name__ == "__main__":
    if not TOKEN: print("No DISCORD_TOKEN found."); exit(1)
    print("Starting real-time bot (Steam: 2min, Other sources: 10min)...")
    bot.run(TOKEN, log_handler=None)
