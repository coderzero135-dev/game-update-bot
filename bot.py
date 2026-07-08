"""Game Update Bot - Discord Bot"""

import asyncio
import logging
import logging.handlers
import threading
import time
import traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config import (
    TOKEN,
    BOARD_UPDATE_INTERVAL,
    WEB_PORT,
    WEB_HOST,
    LOG_FILE,
    LOG_LEVEL,
    load_games,
)
from database import init_db, config_get, config_set
from sources import fetch_all_games
from web import create_web_server

logger = logging.getLogger("bot")
logger.setLevel(LOG_LEVEL)

# Console handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logger.addHandler(ch)

# File handler
try:
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)
except Exception:
    pass

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
    "RSS": "\U0001f4f0", "Build": "\U0001f4e6", "—": "",
}

_last_fetch_time = 0.0
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def fmt(ts: int) -> str:
    if not ts:
        return "--"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
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
        return f"{diff.days // 7}w"
    if diff.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%b %Y")


def rel_time(ts: float) -> str:
    if not ts:
        return "?"
    secs = int(time.time() - ts)
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h ago"


def build_board(results: list[dict]) -> list[discord.Embed]:
    results = sorted(results, key=lambda x: x["ts"] or 0, reverse=True)
    now_ts = datetime.now(timezone.utc).timestamp()

    today = [r for r in results if r["ts"] and (now_ts - r["ts"]) < 86400]
    week = [r for r in results if r["ts"] and 86400 <= (now_ts - r["ts"]) < 604800]
    older = [r for r in results if r["ts"] and (now_ts - r["ts"]) >= 604800]
    none = [r for r in results if not r["ts"]]

    def fmt_list(items, icon):
        lines = []
        for r in items:
            cat = CAT_ICONS.get(r.get("tag", ""), "")
            si = SRC_ICONS.get(r.get("src", ""), "")
            lines.append(f"{icon} `{fmt(r['ts']):>5}` {cat} **{r['name']}** {si}")
        return lines

    embeds = []
    recent = fmt_list(today, "\U0001f7e2") + fmt_list(week, "\U0001f7e1")
    if recent:
        desc = "\n".join(recent[:60])
        if len(recent) > 60:
            desc += f"\n*...and {len(recent) - 60} more*"
        embeds.append(discord.Embed(
            title="Recently Updated",
            description=desc,
            color=0x3FB950,
            timestamp=datetime.now(timezone.utc),
        ))

    rest = fmt_list(older, "\U0001f534") + fmt_list(none, "\u26ab")
    if rest:
        for i in range(0, len(rest), 75):
            chunk = rest[i:i + 75]
            embed = discord.Embed(
                title="All Games" if i == 0 else "",
                description="\n".join(chunk),
                color=0x30363D,
            )
            if i + 75 >= len(rest):
                ago = rel_time(_last_fetch_time) if _last_fetch_time else "?"
                embed.set_footer(text=f"{len(results)} games | checked {ago} | 🎮=Steam 💬=Reddit 🌐=Web 📰=RSS")
            embeds.append(embed)

    return embeds or [discord.Embed(title="No data", description="Fetching...", color=0x30363D)]


# --- Events ---

@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    synced = await bot.tree.sync()
    logger.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
    pinned_updater.start()
    asyncio.create_task(prefetch())
    logger.info("Ready. Board updates every %d minutes.", BOARD_UPDATE_INTERVAL)


@bot.event
async def on_command_error(ctx, error):
    logger.error("Command error: %s", error)


# --- Prefetch ---

async def prefetch():
    logger.info("Prefetching all sources...")
    global _last_fetch_time
    try:
        t0 = time.time()
        r = await fetch_all_games()
        _last_fetch_time = time.time()
        ok = sum(1 for x in r if x["ts"])
        logger.info("Prefetch: %d/%d games in %.1fs", ok, len(r), time.time() - t0)
    except Exception as e:
        logger.error("Prefetch failed: %s", e)


# --- Slash Commands ---

@bot.tree.command(name="ping", description="Check bot status")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)


@bot.tree.command(name="updates", description="Show all game updates")
async def updates_cmd(interaction: discord.Interaction, game: str = None):
    await interaction.response.defer()
    try:
        results = await fetch_all_games()
        if game:
            q = game.lower()
            results = [r for r in results if q in r["name"].lower()]
        if not results:
            await interaction.followup.send("No games found.")
            return
        for embed in build_board(results):
            await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error("updates command: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="latest", description="Full details for a game")
async def latest_cmd(interaction: discord.Interaction, game: str):
    await interaction.response.defer()
    try:
        results = await fetch_all_games()
        q = game.lower()
        matches = [(r, _score(q, r["name"].lower())) for r in results]
        matches = [m for m in matches if m[1] > 0]
        matches.sort(key=lambda x: x[1], reverse=True)
        if not matches:
            await interaction.followup.send(f"No game matching `{game}`.")
            return
        r = matches[0][0]
        si = SRC_ICONS.get(r.get("src", ""), "")
        embed = discord.Embed(
            title=f"{CAT_ICONS.get(r.get('tag', ''), '')} {r['name']}",
            description=f"Source: {r.get('src', '?')} {si}\nLast update: **{fmt(r['ts'])}**",
            color=0x1F6FEB,
        )
        if r.get("url"):
            embed.add_field(name="Link", value=r["url"], inline=False)
        if r.get("title"):
            embed.add_field(name="Latest", value=r["title"][:256], inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error("latest command: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")


def _score(q: str, n: str) -> int:
    if q == n:
        return 100
    if n.startswith(q):
        return 90
    if q in n:
        return 70
    return sum(20 for w in q.split() if any(w in nw for nw in n.split()))


@bot.tree.command(name="pinboard", description="Create auto-updating status board")
@commands.has_permissions(manage_messages=True)
async def pinboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        results = await fetch_all_games()
        embeds = build_board(results)
        msg = await interaction.channel.send(embeds=embeds[:10])
        try:
            await msg.pin()
        except Exception:
            pass
        config_set("channel_id", interaction.channel_id)
        config_set("message_id", msg.id)
        config_set("last_ts", {r["id"]: r["ts"] or 0 for r in results})
        await interaction.followup.send(f"Board pinned. Refreshes every **{BOARD_UPDATE_INTERVAL} minutes**.")
    except Exception as e:
        logger.error("pinboard command: %s", traceback.format_exc())
        await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="stopboard", description="Stop the auto-updating board")
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
        if q in gname.lower():
            matches.append((gname, "Steam"))
    for key, gname in games.get("non_steam", {}).items():
        if q in gname.lower():
            matches.append((gname, "Non-Steam"))
    if not matches:
        await interaction.response.send_message("No matches.")
        return
    lines = [f"- {n} ({src})" for n, src in sorted(matches)[:25]]
    await interaction.response.send_message("**Games:**\n" + "\n".join(lines))


@bot.tree.command(name="refresh", description="Clear cache and re-fetch all sources")
async def refresh_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    from database import cache_clear
    cache_clear()
    results = await fetch_all_games()
    ok = sum(1 for r in results if r["ts"])
    await interaction.followup.send(f"Cleared. Fetched {ok}/{len(results)} games fresh.")


# --- Background Updater ---

@tasks.loop(minutes=BOARD_UPDATE_INTERVAL)
async def pinned_updater():
    global _last_fetch_time
    cid = config_get("channel_id", 0)
    mid = config_get("message_id", 0)
    if not cid or not mid:
        return
    channel = bot.get_channel(cid)
    if not channel:
        return
    try:
        pinned_msg = await channel.fetch_message(mid)
    except Exception:
        return

    try:
        results = await fetch_all_games()
        _last_fetch_time = time.time()
    except Exception as e:
        logger.error("Updater fetch failed: %s", e)
        return

    last_ts = config_get("last_ts", {})
    alerts = []
    for r in results:
        rid = r["id"]
        ts = r["ts"] or 0
        prev = last_ts.get(rid, 0)
        if ts > prev and prev > 0:
            si = SRC_ICONS.get(r.get("src", ""), "")
            cat = CAT_ICONS.get(r.get("tag", ""), "")
            alerts.append(f"{cat} **{r['name']}** updated ({fmt(ts)}) via {r.get('src', '?')} {si}")
        last_ts[rid] = ts

    embeds = build_board(results)
    try:
        await pinned_msg.edit(embeds=embeds[:10])
    except Exception as e:
        logger.error("Edit pin failed: %s", e)

    if alerts:
        try:
            await channel.send(
                embed=discord.Embed(
                    title="\U0001f514 New Updates",
                    description="\n".join(alerts[:20]),
                    color=0x3FB950,
                ),
                delete_after=300,
            )
        except Exception as e:
            logger.error("Alert send failed: %s", e)

    config_set("last_ts", last_ts)


@pinned_updater.before_loop
async def _before_updater():
    await bot.wait_until_ready()


# --- Run ---

def main():
    if not TOKEN:
        logger.critical("No DISCORD_TOKEN found.")
        return

    # Initialize database
    init_db()

    # Start web dashboard in a thread
    httpd = create_web_server(WEB_PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info("Web dashboard on http://%s:%d", WEB_HOST, WEB_PORT)

    logger.info("Starting bot...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Invalid token.")


if __name__ == "__main__":
    main()
