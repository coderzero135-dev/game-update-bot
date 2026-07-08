"""Game Update Bot - Discord Bot"""

import asyncio, logging, logging.handlers, threading, time, traceback, re, json
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks

from config import TOKEN, BOARD_UPDATE_INTERVAL, WEB_PORT, WEB_HOST, LOG_FILE, LOG_LEVEL, load_games
from database import (
    init_db, config_get, config_set, cache_clear,
    watch_add, watch_remove, watch_get_users, watch_get_games,
    role_add, role_remove, role_get_for_game,
    history_get,
)
from sources import fetch_all_games
from web import create_web_server

logger = logging.getLogger("bot")
logger.setLevel(LOG_LEVEL)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logger.addHandler(ch)
try:
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)
except: pass

CAT_ICONS = {
    "fps": "\U0001f52b", "br": "\U0001f3af", "survival": "\U0001faa8",
    "mmo": "\U0001f310", "hero": "\U0001f9d1\u200d\U0001f4bb", "moba": "\u2694\ufe0f",
    "arpg": "\U0001f5e1\ufe0f", "openworld": "\U0001f30d", "sim": "\U0001f3cd\ufe0f",
    "horror": "\U0001f47b", "sports": "\u26bd", "looter": "\U0001f4e6",
    "horde": "\U0001f41b", "rogue": "\U0001f3b2", "party": "\U0001f389",
    "rpg": "\U0001f4dc", "dungeon": "\U0001f9d9", "gacha": "\U0001f3b0",
    "adventure": "\u26f5", "other": "\U0001f3ae",
}
SRC_ICONS = {
    "Steam": "\U0001f3ae", "Reddit": "\U0001f4ac", "Web": "\U0001f310",
    "RSS": "\U0001f4f0", "Build": "\U0001f4e6", "Sale": "\U0001f4b0", "—": "",
}
CAT_EMOJIS = {v: k for k, v in {
    "fps": "\U0001f52b", "br": "\U0001f3af", "survival": "\U0001faa8",
    "mmo": "\U0001f310", "moba": "\u2694\ufe0f", "arpg": "\U0001f5e1\ufe0f",
    "gacha": "\U0001f3b0", "hero": "\U0001f9d1\u200d\U0001f4bb", "other": "\U0001f3ae",
}.items()}

_last_fetch_time = 0.0
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Helpers ---

def fmt(ts: int) -> str:
    if not ts: return "--"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    if diff.days == 0:
        h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
        if h: return f"{h}h"
        if m: return f"{m}m"
        return "now"
    if diff.days == 1: return "1d"
    if diff.days < 7: return f"{diff.days}d"
    if diff.days < 30: return f"{diff.days//7}w"
    if diff.days < 365: return dt.strftime("%b %d")
    return dt.strftime("%b %Y")

def rel_time(ts: float) -> str:
    if not ts: return "?"
    secs = int(time.time() - ts)
    if secs < 60: return f"{secs}s ago"
    if secs < 3600: return f"{secs//60}m ago"
    return f"{secs//3600}h ago"

def build_board(results: list[dict], category: str = None) -> list[discord.Embed]:
    if category and category in CAT_EMOJIS:
        results = [r for r in results if r.get("tag") == category]
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)
    now_ts = datetime.now(timezone.utc).timestamp()

    today = [r for r in results if r["ts"] and (now_ts - r["ts"]) < 86400]
    week = [r for r in results if r["ts"] and 86400 <= (now_ts - r["ts"]) < 604800]
    older = [r for r in results if r["ts"] and (now_ts - r["ts"]) >= 604800]
    none = [r for r in results if not r["ts"]]

    def fmt_list(items, icon):
        return [f"{icon} `{fmt(r['ts']):>5}` {CAT_ICONS.get(r.get('tag',''),'')} **{r['name']}** {SRC_ICONS.get(r.get('src',''),'')}" for r in items]

    embeds = []
    recent = fmt_list(today, "\U0001f7e2") + fmt_list(week, "\U0001f7e1")
    if recent:
        d = "\n".join(recent[:60])
        if len(recent) > 60: d += f"\n*...and {len(recent)-60} more*"
        embeds.append(discord.Embed(title="Recently Updated" + (f" ({CAT_ICONS[category]} {category})" if category else ""), description=d, color=0x3FB950, timestamp=datetime.now(timezone.utc)))

    rest = fmt_list(older, "\U0001f534") + fmt_list(none, "\u26ab")
    if rest:
        for i in range(0, len(rest), 75):
            chunk = rest[i:i+75]
            embed = discord.Embed(title="All Games" if i == 0 else "", description="\n".join(chunk), color=0x30363D)
            if i + 75 >= len(rest):
                ago = rel_time(_last_fetch_time)
                embed.set_footer(text=f"{len(results)} games | checked {ago} | 🎮Steam 💬Reddit 🌐Web 📰RSS")
            embeds.append(embed)
    return embeds or [discord.Embed(title="No data", description="Fetching...", color=0x30363D)]

# --- Board View (Buttons) ---

class BoardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CategorySelect())
        self.add_item(RefreshButton())

class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Refresh", emoji="\U0001f504", custom_id="board_refresh")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = await interaction.channel.send("Fetching...")
        results = await fetch_all_games()
        embeds = build_board(results)
        await status.delete()
        try:
            pinned = await interaction.channel.fetch_message(interaction.message.id)
            await pinned.edit(embeds=embeds[:10], view=BoardView())
        except: pass
        await interaction.followup.send("Refreshed.", ephemeral=True)

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="All", value="all", emoji="\U0001f3ae", default=True),
            discord.SelectOption(label="FPS", value="fps", emoji="\U0001f52b"),
            discord.SelectOption(label="Battle Royale", value="br", emoji="\U0001f3af"),
            discord.SelectOption(label="Survival", value="survival", emoji="\U0001faa8"),
            discord.SelectOption(label="MMO", value="mmo", emoji="\U0001f310"),
            discord.SelectOption(label="MOBA", value="moba", emoji="\u2694\ufe0f"),
            discord.SelectOption(label="ARPG", value="arpg", emoji="\U0001f5e1\ufe0f"),
            discord.SelectOption(label="Gacha", value="gacha", emoji="\U0001f3b0"),
            discord.SelectOption(label="Hero", value="hero", emoji="\U0001f9d1\u200d\U0001f4bb"),
        ]
        super().__init__(placeholder="Filter by category...", options=options, custom_id="board_category", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat = self.values[0] if self.values[0] != "all" else None
        results = await fetch_all_games()
        embeds = build_board(results, cat)
        await interaction.message.edit(embeds=embeds[:10], view=BoardView())
        await interaction.followup.send(f"Showing: {cat or 'All'}", ephemeral=True)

# --- Autocomplete ---

async def game_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice]:
    games = load_games()
    choices = []
    q = current.lower()
    for appid, name in games.get("steam", {}).items():
        if q in name.lower() and len(choices) < 25:
            choices.append(discord.app_commands.Choice(name=name, value=name))
    for key, name in games.get("non_steam", {}).items():
        if q in name.lower() and len(choices) < 25:
            choices.append(discord.app_commands.Choice(name=name, value=name))
    return choices

# --- Events ---

@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)
    bot.add_view(BoardView())
    # Force full resync — clears stale commands
    try:
        bot.tree.clear_commands(guild=None)
        synced = await bot.tree.sync()
        logger.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
    except Exception as e:
        logger.error("Sync failed: %s", e)
    pinned_updater.start()
    daily_digest.start()
    asyncio.create_task(prefetch())
    logger.info("Ready. Board: %dmin. Digest: daily.", BOARD_UPDATE_INTERVAL)

async def prefetch():
    global _last_fetch_time
    try:
        t0 = time.time()
        r = await fetch_all_games()
        _last_fetch_time = time.time()
        ok = sum(1 for x in r if x["ts"])
        logger.info("Prefetch: %d/%d in %.1fs", ok, len(r), time.time()-t0)
    except Exception as e:
        logger.error("Prefetch failed: %s", e)

# --- Progress bar fetch ---

async def fetch_with_progress(interaction, message) -> list[dict]:
    """Fetch games with a progress bar that edits the loading message."""
    total = len(steam_games) + len(non_steam_games)
    for i in range(1, 6):
        bar = ("\u2588" * i) + ("\u2591" * (5 - i))
        await message.edit(content=f"Scanning sources... {bar} {i*20}%")
        await asyncio.sleep(0.3)
    results = await fetch_all_games()
    return results

STEAM_GAME_LIST = None
NON_STEAM_LIST = None

def _init_game_lists():
    global steam_games, non_steam_games
    if STEAM_GAME_LIST is None:
        g = load_games()
        steam_games = g.get("steam", {})
        non_steam_games = g.get("non_steam", {})
_init_game_lists()
steam_games = load_games().get("steam", {})
non_steam_games = load_games().get("non_steam", {})

# --- Commands ---

@bot.tree.command(name="ping", description="Check bot status")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

@bot.tree.command(name="updates", description="Show all game updates")
@discord.app_commands.autocomplete(game=game_autocomplete)
async def updates_cmd(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    msg = await interaction.followup.send("Scanning... \u2591\u2591\u2591\u2591\u2591")
    try:
        results = await fetch_with_progress(interaction, msg)
        await msg.delete()
        if game:
            q = game.lower()
            results = [r for r in results if q in r["name"].lower()]
        if not results:
            await interaction.followup.send("No games found.")
            return
        for embed in build_board(results):
            await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error("updates: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="latest", description="Full details for a game")
@discord.app_commands.autocomplete(game=game_autocomplete)
async def latest_cmd(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    msg = await interaction.followup.send("Checking...")
    try:
        results = await fetch_all_games()
        await msg.delete()
        q = game.lower()
        matches = [(r, s) for r in results if (s := _score(q, r["name"].lower())) > 0]
        matches.sort(key=lambda x: x[1], reverse=True)
        if not matches:
            await interaction.followup.send(f"No game matching `{game}`.")
            return
        r = matches[0][0]
        embed = discord.Embed(
            title=f"{CAT_ICONS.get(r.get('tag',''),'')} {r['name']}",
            description=f"Source: {r.get('src','?')} {SRC_ICONS.get(r.get('src',''),'')}\nLast update: **{fmt(r['ts'])}**",
            color=0x1F6FEB,
        )
        if r.get("url"): embed.add_field(name="Link", value=r["url"], inline=False)
        if r.get("title"): embed.add_field(name="Latest", value=r["title"][:256], inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error("latest: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="history", description="Show update history for a game")
@discord.app_commands.autocomplete(game=game_autocomplete)
async def history_cmd(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    games = load_games()
    # Find game_id from name
    gid = None
    for appid, name in games.get("steam", {}).items():
        if name.lower() == game.lower():
            gid = appid; break
    if not gid:
        for key, name in games.get("non_steam", {}).items():
            if name.lower() == game.lower():
                gid = key; break
    if not gid:
        # fuzzy match
        results = await fetch_all_games()
        matches = [(r, _score(game.lower(), r["name"].lower())) for r in results]
        matches = [m for m in matches if m[1] > 0]
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            gid = matches[0][0]["id"]
            game = matches[0][0]["name"]

    if not gid:
        await interaction.followup.send(f"No game matching `{game}`.")
        return

    history = history_get(gid, 10)
    if not history:
        await interaction.followup.send(f"No update history for **{game}** yet. Try `/refresh` first.")
        return

    desc = "\n".join(
        f"`{datetime.fromtimestamp(h['ts'], tz=timezone.utc).strftime('%b %d')}` {SRC_ICONS.get(h['src'], '')} {h['title'][:100]}"
        for h in history
    )
    embed = discord.Embed(title=f"Update History: {game}", description=desc, color=0x1F6FEB)
    await interaction.followup.send(embed=embed)

def _score(q: str, n: str) -> int:
    if q == n: return 100
    if n.startswith(q): return 90
    if q in n: return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))

@bot.tree.command(name="watch", description="Get DMed when a game updates")
@discord.app_commands.autocomplete(game=game_autocomplete)
async def watch_cmd(interaction: discord.Interaction, game: str):
    games = load_games()
    gid = None
    for appid, name in games.get("steam", {}).items():
        if name.lower() == game.lower(): gid = appid; break
    if not gid:
        for key, name in games.get("non_steam", {}).items():
            if name.lower() == game.lower(): gid = key; break
    if not gid:
        await interaction.response.send_message(f"Game `{game}` not found.", ephemeral=True)
        return
    watch_add(interaction.user.id, gid)
    await interaction.response.send_message(f"You'll be DMed when **{game}** updates.", ephemeral=True)

@bot.tree.command(name="unwatch", description="Stop watching a game")
@discord.app_commands.autocomplete(game=game_autocomplete)
async def unwatch_cmd(interaction: discord.Interaction, game: str):
    games = load_games()
    for appid, name in games.get("steam", {}).items():
        if name.lower() == game.lower():
            watch_remove(interaction.user.id, appid)
            await interaction.response.send_message(f"Stopped watching **{game}**.", ephemeral=True)
            return
    for key, name in games.get("non_steam", {}).items():
        if name.lower() == game.lower():
            watch_remove(interaction.user.id, key)
            await interaction.response.send_message(f"Stopped watching **{game}**.", ephemeral=True)
            return
    await interaction.response.send_message(f"Game `{game}` not found.", ephemeral=True)

@bot.tree.command(name="mywatches", description="List games you're watching")
async def mywatches_cmd(interaction: discord.Interaction):
    gids = watch_get_games(interaction.user.id)
    if not gids:
        await interaction.response.send_message("You're not watching any games.", ephemeral=True)
        return
    games = load_games()
    names = []
    for gid in gids:
        n = games.get("steam", {}).get(gid) or games.get("non_steam", {}).get(gid) or gid
        names.append(n)
    await interaction.response.send_message("**Watching:**\n" + "\n".join(f"- {n}" for n in sorted(names)), ephemeral=True)

@bot.tree.command(name="setrole", description="Ping a role when a game updates")
@commands.has_permissions(manage_roles=True)
@discord.app_commands.autocomplete(game=game_autocomplete)
async def setrole_cmd(interaction: discord.Interaction, game: str, role: discord.Role):
    games = load_games()
    gid = None
    for appid, name in games.get("steam", {}).items():
        if name.lower() == game.lower(): gid = appid; break
    if not gid:
        for key, name in games.get("non_steam", {}).items():
            if name.lower() == game.lower(): gid = key; break
    if not gid:
        await interaction.response.send_message(f"Game `{game}` not found.", ephemeral=True)
        return
    role_add(role.id, gid, interaction.channel_id)
    await interaction.response.send_message(f"{role.mention} will be pinged when **{game}** updates.")

@bot.tree.command(name="removerole", description="Remove role ping for a game")
@commands.has_permissions(manage_roles=True)
@discord.app_commands.autocomplete(game=game_autocomplete)
async def removerole_cmd(interaction: discord.Interaction, game: str, role: discord.Role):
    games = load_games()
    for appid, name in games.get("steam", {}).items():
        if name.lower() == game.lower():
            role_remove(role.id, appid)
            await interaction.response.send_message(f"Removed ping for **{game}**.", ephemeral=True)
            return
    for key, name in games.get("non_steam", {}).items():
        if name.lower() == game.lower():
            role_remove(role.id, key)
            await interaction.response.send_message(f"Removed ping for **{game}**.", ephemeral=True)
            return
    await interaction.response.send_message(f"Game `{game}` not found.", ephemeral=True)

@bot.tree.command(name="addgame", description="Add a game from Steam URL or app ID")
async def addgame_cmd(interaction: discord.Interaction, steam_url_or_id: str):
    # Extract app ID from URL or direct ID
    m = re.search(r"(?:app/|appid=)(\d+)", steam_url_or_id)
    appid = m.group(1) if m else steam_url_or_id.strip()
    if not appid.isdigit():
        await interaction.response.send_message("Invalid. Provide a Steam app ID or store URL.", ephemeral=True)
        return

    # Verify the app exists
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://store.steampowered.com/api/appdetails?appids={appid}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    await interaction.response.send_message("Could not verify the game.", ephemeral=True)
                    return
                data = await r.json()
                app = data.get(appid, {}).get("data")
                if not app or not data.get(appid, {}).get("success"):
                    await interaction.response.send_message(f"App ID `{appid}` not found on Steam.", ephemeral=True)
                    return
                name = app.get("name", appid)
        except Exception:
            await interaction.response.send_message("Failed to verify. Check the ID and try again.", ephemeral=True)
            return

    # Save to custom games
    cfg = config_get("custom_games", {})
    cfg[appid] = name
    config_set("custom_games", cfg)

    await interaction.response.send_message(f"Added **{name}** (`{appid}`) to tracking. Will appear on next refresh.", ephemeral=True)

@bot.tree.command(name="pinboard", description="Create auto-updating board with buttons")
@commands.has_permissions(manage_messages=True)
async def pinboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg_progress = await interaction.followup.send("Building board... \u2591\u2591\u2591\u2591\u2591")
    try:
        results = await fetch_with_progress(interaction, msg_progress)
        await msg_progress.delete()
        embeds = build_board(results)
        msg = await interaction.channel.send(embeds=embeds[:10], view=BoardView())
        try: await msg.pin()
        except: pass
        config_set("channel_id", interaction.channel_id)
        config_set("message_id", msg.id)
        config_set("last_ts", {r["id"]: r["ts"] or 0 for r in results})
        await interaction.followup.send(f"Board pinned with Refresh + Filter buttons. Updates every **{BOARD_UPDATE_INTERVAL} min**.")
    except Exception as e:
        logger.error("pinboard: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="stopboard", description="Stop the board")
@commands.has_permissions(manage_messages=True)
async def stopboard_cmd(interaction: discord.Interaction):
    config_set("channel_id", 0)
    config_set("message_id", 0)
    await interaction.response.send_message("Stopped.")

@bot.tree.command(name="search", description="Search tracked games")
async def search_cmd(interaction: discord.Interaction, name: str):
    games = load_games()
    q = name.lower()
    matches = []
    for appid, gname in games.get("steam", {}).items(): 
        if q in gname.lower(): matches.append((gname, "Steam"))
    for key, gname in games.get("non_steam", {}).items(): 
        if q in gname.lower(): matches.append((gname, "Non-Steam"))
    if not matches:
        await interaction.response.send_message("No matches.")
        return
    lines = [f"- {n} ({src})" for n, src in sorted(matches)[:25]]
    await interaction.response.send_message("**Games:**\n" + "\n".join(lines))

@bot.tree.command(name="refresh", description="Clear cache and re-fetch")
async def refresh_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    msg = await interaction.followup.send("Clearing cache...")
    cache_clear()
    results = await fetch_all_games()
    await msg.delete()
    ok = sum(1 for r in results if r["ts"])
    await interaction.followup.send(f"Fetched {ok}/{len(results)} games fresh from all sources.")

@bot.tree.command(name="digest", description="Set daily digest channel and hour")
@commands.has_permissions(manage_channels=True)
async def digest_cmd(interaction: discord.Interaction, hour: int = 12):
    if hour < 0 or hour > 23:
        await interaction.response.send_message("Hour must be 0-23.", ephemeral=True)
        return
    config_set("digest_channel", interaction.channel_id)
    config_set("digest_hour", hour)
    await interaction.response.send_message(f"Daily digest will be posted here at **{hour}:00 UTC**.")

# --- Board Updater ---

@tasks.loop(minutes=BOARD_UPDATE_INTERVAL)
async def pinned_updater():
    global _last_fetch_time
    cid = config_get("channel_id", 0)
    mid = config_get("message_id", 0)
    if not cid or not mid: return
    channel = bot.get_channel(cid)
    if not channel: return
    try: pinned_msg = await channel.fetch_message(mid)
    except: return

    try:
        results = await fetch_all_games()
        _last_fetch_time = time.time()
    except Exception as e:
        logger.error("Updater fetch: %s", e)
        return

    last_ts = config_get("last_ts", {})
    alerts = []
    for r in results:
        rid, ts = r["id"], r["ts"] or 0
        prev = last_ts.get(rid, 0)
        if ts > prev and prev > 0:
            si = SRC_ICONS.get(r.get("src",""),"")
            cat = CAT_ICONS.get(r.get("tag",""),"")
            alerts.append((r, f"{cat} **{r['name']}** updated ({fmt(ts)}) via {r.get('src','?')} {si}"))
        last_ts[rid] = ts

    embeds = build_board(results)
    try: await pinned_msg.edit(embeds=embeds[:10], view=BoardView())
    except Exception as e: logger.error("Edit: %s", e)

    # Send alerts with watches and role pings
    if alerts:
        alert_lines = []
        for r, line in alerts:
            alert_lines.append(line)
            # DM watchers
            for uid in watch_get_users(r["id"]):
                try:
                    user = await bot.fetch_user(uid)
                    embed = discord.Embed(
                        title=f"\U0001f514 {r['name']} Updated",
                        description=f"Source: {r.get('src','?')}\n{r.get('title','')[:200]}\n{r.get('url','')}",
                        color=0x3FB950,
                    )
                    await user.send(embed=embed)
                except: pass
            # Role pings
            for role_id, ch_id in role_get_for_game(r["id"]):
                try:
                    ch = bot.get_channel(ch_id)
                    if ch:
                        await ch.send(
                            f"<@&{role_id}> **{r['name']}** updated ({fmt(r['ts'])})",
                            delete_after=300,
                        )
                except: pass

        if alert_lines:
            await channel.send(
                embed=discord.Embed(title="\U0001f514 New Updates", description="\n".join(alert_lines[:20]), color=0x3FB950),
                delete_after=300,
            )

    config_set("last_ts", last_ts)

@pinned_updater.before_loop
async def _up(): await bot.wait_until_ready()

# --- Daily Digest ---

@tasks.loop(hours=24)
async def daily_digest():
    hour = config_get("digest_hour")
    if hour is None: return
    now_utc = datetime.now(timezone.utc).hour
    if now_utc != hour: return

    cid = config_get("digest_channel", 0)
    if not cid: return
    channel = bot.get_channel(cid)
    if not channel: return

    results = await fetch_all_games()
    now_ts = datetime.now(timezone.utc).timestamp()
    today_updates = [r for r in results if r["ts"] and (now_ts - r["ts"]) < 86400]

    if today_updates:
        desc = "\n".join(
            f"{CAT_ICONS.get(r.get('tag',''),'')} **{r['name']}** — {fmt(r['ts'])} "
            f"{SRC_ICONS.get(r.get('src',''),'')}"
            for r in sorted(today_updates, key=lambda x: x["ts"] or 0, reverse=True)
        )
        embed = discord.Embed(
            title="Daily Digest — Today's Updates",
            description=desc[:4000] or "No updates today.",
            color=0x1F6FEB,
            timestamp=datetime.now(timezone.utc),
        )
        await channel.send(embed=embed)
    else:
        await channel.send("No game updates in the last 24 hours.")

@daily_digest.before_loop
async def _dig(): await bot.wait_until_ready()

# --- Run ---

def main():
    if not TOKEN:
        logger.critical("No DISCORD_TOKEN found.")
        return
    init_db()
    httpd = create_web_server(WEB_PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info("Web dashboard: http://%s:%d", WEB_HOST, WEB_PORT)
    logger.info("Starting bot...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Invalid token.")

if __name__ == "__main__":
    main()
