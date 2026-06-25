import asyncio
from typing import Optional

import aiohttp


BASE_URL = "https://api.opendota.com/api"

BUSY_STATUSES = {429, 500, 502, 503, 504}


class OpenDotaBusyError(Exception):
    pass


class OpenDotaNotFoundError(Exception):
    pass


async def _request_json(path: str):
    timeout = aiohttp.ClientTimeout(total=12)

    for attempt in range(2):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{BASE_URL}{path}") as r:
                    if r.status == 200:
                        return await r.json()

                    if r.status == 404:
                        raise OpenDotaNotFoundError()

                    if r.status in BUSY_STATUSES:
                        raise OpenDotaBusyError()

                    return None

        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            raise OpenDotaBusyError()

        except OpenDotaBusyError:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            raise

    return None


async def get_player(account_id: int) -> Optional[dict]:
    return await _request_json(f"/players/{account_id}")


async def get_player_wl(account_id: int) -> Optional[dict]:
    return await _request_json(f"/players/{account_id}/wl")


async def get_player_heroes(account_id: int) -> Optional[list]:
    data = await _request_json(f"/players/{account_id}/heroes")

    if data:
        data.sort(key=lambda h: h.get("games", 0), reverse=True)

    return data


async def get_recent_matches(account_id: int) -> Optional[list]:
    return await _request_json(f"/players/{account_id}/recentMatches")


async def get_match(match_id: int) -> Optional[dict]:
    return await _request_json(f"/matches/{match_id}")


async def search_player(query: str) -> Optional[list]:
    return await _request_json(f"/search?q={query}")


async def get_heroes() -> Optional[list]:
    return await _request_json("/heroes")