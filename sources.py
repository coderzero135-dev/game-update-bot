"""Game Update Bot - Data Sources"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from xml.etree import ElementTree
from typing import Optional

import aiohttp

from config import (
    STEAM_CACHE_TTL,
    EXTERNAL_CACHE_TTL,
    BUILD_CHECK_TTL,
    STEAM_SEMAPHORE,
    load_games,
)
from database import cache_get, cache_set, build_version_get, build_version_set

logger = logging.getLogger(__name__)

# --- Helpers ---

def parse_rss_date(text: str) -> float | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    return None


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# --- Source: Steam RSS Feed ---

async def source_steam(
    appid: str, session: aiohttp.ClientSession, sem: asyncio.Semaphore
) -> tuple[int, str, str, str]:
    async with sem:
        try:
            url = f"https://store.steampowered.com/feeds/news/app/{appid}/"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    logger.debug("Steam RSS %s: HTTP %d", appid, r.status)
                    return 0, "", "", "—"
                root = ElementTree.fromstring(await r.text())
                for item in root.iter("item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")
                    desc_el = item.find("description")
                    if title_el is None or pub_el is None:
                        continue
                    ts = parse_rss_date(pub_el.text or "")
                    if ts is None:
                        continue
                    link = (link_el.text or "") if link_el is not None else ""
                    body = strip_html((desc_el.text or "") if desc_el is not None else "")[:200]
                    return int(ts), link, body, "Steam"
        except Exception as e:
            logger.debug("Steam RSS %s error: %s", appid, e)
    return 0, "", "", "—"


# --- Source: Google News RSS ---

async def source_google_news(
    query: str, session: aiohttp.ClientSession, sem: asyncio.Semaphore
) -> tuple[int, str, str, str]:
    async with sem:
        try:
            q = query.replace(" ", "+")
            url = f"https://news.google.com/rss/search?q={q}+patch+update&hl=en-US&gl=US&ceid=US:en"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status != 200:
                    return 0, "", "", "—"
                root = ElementTree.fromstring(await r.text())
                for item in root.iter("item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")
                    if title_el is None or pub_el is None:
                        continue
                    ts = parse_rss_date(pub_el.text or "")
                    if ts is None:
                        continue
                    link = (link_el.text or "") if link_el is not None else ""
                    return int(ts), link, strip_html(title_el.text or "")[:200], "Web"
        except Exception as e:
            logger.debug("Google News '%s' error: %s", query, e)
    return 0, "", "", "—"


# --- Source: Reddit ---

async def source_reddit(
    subreddit: str, session: aiohttp.ClientSession, sem: asyncio.Semaphore
) -> tuple[int, str, str, str]:
    async with sem:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            headers = {"User-Agent": "GameUpdateBot/2.0"}
            params = {"q": "patch OR update", "sort": "new", "restrict_sr": "on", "limit": 3, "t": "month"}
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status != 200:
                    return 0, "", "", "—"
                data = await r.json()
                posts = data.get("data", {}).get("children", [])
                if not posts:
                    return 0, "", "", "—"
                p = posts[0]["data"]
                ts = int(p.get("created_utc", 0))
                link = f"https://reddit.com{p.get('permalink', '')}"
                title = strip_html(p.get("title", ""))[:200]
                return ts, link, title, "Reddit"
        except Exception as e:
            logger.debug("Reddit r/%s error: %s", subreddit, e)
    return 0, "", "", "—"


# --- Source: Build Version Tracker ---

async def source_build(
    appid: str, session: aiohttp.ClientSession, sem: asyncio.Semaphore
) -> tuple[int, str, str, str]:
    async with sem:
        try:
            url = "https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/"
            params = {"appid": appid, "version": 0}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=4)) as r:
                if r.status != 200:
                    return 0, "", "", "—"
                data = await r.json()
                resp = data.get("response", {})
                if not resp.get("success"):
                    return 0, "", "", "—"
                ver = resp.get("required_version")
                if ver is None:
                    return 0, "", "", "—"
                msg = resp.get("message", "")
                prev = build_version_get(appid)
                build_version_set(appid, ver, msg)
                if prev and prev["version"] != ver:
                    logger.info("Build change %s: %s → %s", appid, prev["version"], ver)
                    return int(time.time()), "", f"Build {prev['version']} → {ver}", "Build"
        except Exception as e:
            logger.debug("Build check %s error: %s", appid, e)
    return 0, "", "", "—"


# --- Source: Gaming RSS Feeds ---

_GAMING_RSS_CACHE: dict = {"data": None, "ts": 0}

async def source_gaming_rss(
    session: aiohttp.ClientSession, game_names: dict[str, str]
) -> list[tuple[str, int, str, str, str]]:
    """Fetch major gaming RSS feeds and return matches against tracked game names."""
    now = time.time()
    if _GAMING_RSS_CACHE["data"] is not None and now - _GAMING_RSS_CACHE["ts"] < EXTERNAL_CACHE_TTL:
        return _GAMING_RSS_CACHE["data"]

    feeds = [
        "https://www.pcgamer.com/rss/",
        "https://feeds.feedburner.com/ign/all",
        "https://www.eurogamer.net/feed",
    ]
    results: list[tuple[str, int, str, str, str]] = []
    sem = asyncio.Semaphore(3)

    async def fetch_feed(url: str):
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if r.status != 200:
                        return
                    root = ElementTree.fromstring(await r.text())
                    for item in root.iter("item"):
                        title_el = item.find("title")
                        link_el = item.find("link")
                        pub_el = item.find("pubDate")
                        if title_el is None or pub_el is None:
                            continue
                        ttext = (title_el.text or "").lower()
                        for gid, gname in game_names.items():
                            if gname.lower() in ttext:
                                ts = parse_rss_date(pub_el.text or "")
                                if ts is None:
                                    continue
                                link = (link_el.text or "") if link_el is not None else ""
                                results.append((gid, int(ts), link, strip_html(title_el.text or "")[:200], "RSS"))
                                break
            except Exception as e:
                logger.debug("Gaming RSS %s error: %s", url, e)

    await asyncio.gather(*[fetch_feed(u) for u in feeds])
    _GAMING_RSS_CACHE["data"] = results
    _GAMING_RSS_CACHE["ts"] = now
    logger.debug("Gaming RSS: %d matches from feeds", len(results))
    return results


# --- Fetch All ---

async def fetch_all_games() -> list[dict]:
    """Fetch updates for all tracked games from all sources."""
    games = load_games()
    steam_games = games.get("steam", {})
    non_steam = games.get("non_steam", {})

    # Build name lookup for RSS matching
    all_names = {}
    all_names.update(steam_games)
    all_names.update(non_steam)

    # Non-steam subreddit mapping
    non_steam_reddit = {
        "valorant": "VALORANT",
        "fortnite": "FortNiteBR",
        "tarkov": "EscapefromTarkov",
        "genshin": "Genshin_Impact",
        "starrail": "HonkaiStarRail",
        "wuwa": "WutheringWaves",
        "zzz": "ZZZ_Official",
        "minecraft": "Minecraft",
        "roblox": "roblox",
        "osu": "osugame",
        "lol": "leagueoflegends",
        "fivem": "FiveM",
        "chess": "chess",
    }

    results: list[dict] = []
    lock = asyncio.Lock()
    steam_sem = asyncio.Semaphore(STEAM_SEMAPHORE)
    ext_sem = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        # Fetch gaming RSS feeds once
        rss_matches = await source_gaming_rss(session, all_names)

        async def fetch_one(gid: str, name: str, is_steam: bool = True):
            # Check cache first
            ck = f"g_{gid}"
            cached = cache_get(ck, STEAM_CACHE_TTL)
            if cached:
                async with lock:
                    results.append(cached)
                return

            sources = []
            if is_steam:
                sources.append(source_steam(gid, session, steam_sem))
                sources.append(source_build(gid, session, steam_sem))
                sources.append(source_google_news(name, session, ext_sem))
            else:
                sub = non_steam_reddit.get(gid)
                if sub:
                    sources.append(source_reddit(sub, session, ext_sem))
                sources.append(source_google_news(name, session, ext_sem))

            all_s = await asyncio.gather(*sources)

            best_ts, best_url, best_title, best_src = 0, "", "", "—"
            for ts, url, title, src in all_s:
                if ts > best_ts:
                    best_ts, best_url, best_title, best_src = ts, url, title, src

            # Check RSS feed matches
            for rid, rts, rurl, rtitle, rsrc in rss_matches:
                if rid == gid and rts > best_ts:
                    best_ts, best_url, best_title, best_src = rts, rurl, rtitle, rsrc

            # On fast ticks, retain older cached data from external sources
            if cached and is_steam and best_src in ("Steam", "Build", "—"):
                old = cached
                if old.get("src") not in ("Steam", "Build", "—") and old.get("ts", 0) > best_ts:
                    best_ts, best_url, best_title, best_src = old["ts"], old["url"], old["title"], old["src"]

            # Determine tag
            tag = _classify_tag(name)

            entry = {
                "id": gid,
                "name": name,
                "tag": tag,
                "ts": best_ts or 0,
                "url": best_url,
                "title": best_title,
                "src": best_src,
            }
            cache_set(ck, entry)
            async with lock:
                results.append(entry)

        coros = []
        for appid, name in steam_games.items():
            coros.append(fetch_one(appid, name, True))
        for key, name in non_steam.items():
            coros.append(fetch_one(key, name, False))

        await asyncio.gather(*coros)

    return list({r["id"]: r for r in results}.values())


def _classify_tag(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("fps", "call of duty", "battlefield", "counter", "siege", "battlebit", "bodycam", "ready or not", "insurgency", "hell let loose", "gray zone", "arena breakout", "squad", "rogue company", "warface")):
        return "fps"
    if any(k in n for k in ("br", "apex", "pubg", "fortnite", "valorant", "naraka", "bloodhunt", "farlight")):
        return "br"
    if any(k in n for k in ("survival", "rust", "dayz", "ark", "scum", "unturned", "isle", "conan", "deadside", "minecraft", "zomboid")):
        return "survival"
    if any(k in n for k in ("mmo", "albion", "stalcraft", "pioner", "dune")):
        return "mmo"
    if any(k in n for k in ("moba", "deadlock", "smite", "league of legends", "lol")):
        return "moba"
    if any(k in n for k in ("arpg", "path of exile", "elden ring", "wukong", "hades", "monster hunter")):
        return "arpg"
    if any(k in n for k in ("gacha", "genshin", "star rail", "wuwa", "zzz", "snowbreak")):
        return "gacha"
    if any(k in n for k in ("hero", "overwatch", "marvel", "paladins")):
        return "hero"
    if any(k in n for k in ("sim", "war thunder", "arma")):
        return "sim"
    if any(k in n for k in ("openworld", "gta", "rdr", "fivem")):
        return "openworld"
    if any(k in n for k in ("looter", "warframe", "division", "first descendant")):
        return "looter"
    if any(k in n for k in ("horror", "dead by")):
        return "horror"
    if any(k in n for k in ("sports", "rocket", "osu")):
        return "sports"
    if any(k in n for k in ("dungeon", "dark and darker")):
        return "dungeon"
    if any(k in n for k in ("party", "among", "roblox")):
        return "party"
    if any(k in n for k in ("horde", "helldiver")):
        return "horde"
    if any(k in n for k in ("rpg", "baldur")):
        return "rpg"
    if any(k in n for k in ("adventure", "sea of")):
        return "adventure"
    if any(k in n for k in ("rogue",)):
        return "rogue"
    return "other"
