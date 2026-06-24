import aiohttp
from typing import Optional

BASE_URL = "https://api.opendota.com/api"


async def get_player(account_id: int) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/players/{account_id}") as r:
            if r.status == 200:
                return await r.json()
    return None


async def get_player_wl(account_id: int) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/players/{account_id}/wl") as r:
            if r.status == 200:
                return await r.json()
    return None


async def get_player_heroes(account_id: int) -> Optional[list]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/players/{account_id}/heroes"
        ) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    data.sort(key=lambda h: h.get("games", 0), reverse=True)
                return data
    return None


async def get_recent_matches(account_id: int) -> Optional[list]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/players/{account_id}/recentMatches"
        ) as r:
            if r.status == 200:
                return await r.json()
    return None


async def get_role_matches(account_id: int) -> Optional[list]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/players/{account_id}/matches?limit=100&significant=1"
        ) as r:
            if r.status == 200:
                return await r.json()
    return None


async def search_player(query: str) -> Optional[list]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/search?q={query}") as r:
            if r.status == 200:
                return await r.json()
    return None


async def get_heroes() -> Optional[list]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/heroes") as r:
            if r.status == 200:
                return await r.json()
    return None