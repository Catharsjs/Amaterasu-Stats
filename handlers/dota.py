import asyncio
import time
from html import escape

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.opendota import (
    get_player,
    get_player_wl,
    get_player_heroes,
    get_recent_matches,
    search_player,
    get_heroes,
    get_match,
)
from utils.formatters import (
    format_player_stats,
    format_heroes,
    format_matches,
    format_search,
    format_match,
)
from config import (
    ERR_INVALID_ID,
    ERR_PLAYER_NOT_FOUND,
    ERR_NO_RESULTS,
    BRAND_EMOJI,
    BRAND_NAME,
)

router = Router()


class SearchState(StatesGroup):
    waiting_for_query = State()
    waiting_for_match = State()
    waiting_for_stats = State()


_hero_map: dict = {}
_stats_cache: dict = {}
_search_cache: dict = {}

CACHE_TTL = 600
SEARCH_CACHE_TTL = 600


def normalize_name(value: str) -> str:
    return (value or "").strip().lower()


def short_player_name(name: str, max_len: int = 28) -> str:
    name = name or "Player"
    return name if len(name) <= max_len else name[: max_len - 1] + "…"


def rank_search_results(results: list, query: str) -> list:
    q = normalize_name(query)

    def score(player: dict) -> tuple:
        name = normalize_name(player.get("personaname"))

        if name == q:
            return (0, name)
        if name.startswith(q):
            return (1, name)
        if q in name:
            return (2, name)

        return (3, name)

    filtered = [
        player for player in results
        if q in normalize_name(player.get("personaname"))
    ]

    return sorted(filtered, key=score)[:5]


async def load_heroes() -> dict:
    global _hero_map

    if not _hero_map:
        heroes = await get_heroes()
        if heroes:
            _hero_map = {
                h["id"]: h["localized_name"]
                for h in heroes
            }

    return _hero_map


async def get_cached_stats(account_id: int):
    import logging
    logger = logging.getLogger(__name__)

    now = time.time()

    if account_id in _stats_cache:
        cached, ts = _stats_cache[account_id]
        if now - ts < CACHE_TTL:
            logger.info(f"Cache hit for {account_id}")
            return cached

    logger.info(f"Fetching player stats {account_id}...")

    player, wl = await asyncio.gather(
        get_player(account_id),
        get_player_wl(account_id),
    )

    logger.info(f"Player stats done: {account_id}")

    result = (player, wl)
    _stats_cache[account_id] = (result, now)

    return result


async def enrich_search_results_with_rank(results: list) -> list:
    top_results = results[:5]

    async def enrich(player: dict) -> dict:
        account_id = player.get("account_id")
        if not account_id:
            return player

        player_data, _ = await get_cached_stats(int(account_id))

        if player_data:
            player["rank_tier"] = player_data.get("rank_tier")
            player["leaderboard_rank"] = player_data.get("leaderboard_rank")

        return player

    return await asyncio.gather(*(enrich(player) for player in top_results))


async def search_player_fast(query: str) -> list:
    now = time.time()
    cache_key = normalize_name(query)

    if cache_key in _search_cache:
        cached, ts = _search_cache[cache_key]
        if now - ts < SEARCH_CACHE_TTL:
            return cached

    results = await search_player(query)

    if not results:
        return []

    results = rank_search_results(results, query)

    if not results:
        return []

    results = await enrich_search_results_with_rank(results)

    _search_cache[cache_key] = (results, now)

    return results


PRIVATE_MSG = (
    "ℹ️ <i>Інформація недоступна — гравець вимкнув поширення історії матчів</i>"
)


def stats_keyboard(account_id: int, match_id: int | None = None) -> InlineKeyboardMarkup:
    if match_id:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сигнатурні герої",
                    callback_data=f"mh:{match_id}:{account_id}",
                ),
                InlineKeyboardButton(
                    text="Останні матчі",
                    callback_data=f"mm:{match_id}:{account_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ До матчу",
                    callback_data=f"mb:{match_id}",
                ),
            ],
        ])

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сигнатурні герої", callback_data=f"heroes:{account_id}"),
            InlineKeyboardButton(text="Останні матчі", callback_data=f"matches:{account_id}"),
        ]
    ])


def back_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Повернутись", callback_data=f"stats:{account_id}"),
        ]
    ])


def back_to_player_keyboard(match_id: int, account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="◀️ До гравця",
                callback_data=f"mp:{match_id}:{account_id}",
            ),
        ]
    ])


def match_keyboard(match_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Статистика гравця",
                callback_data=f"mplayers:{match_id}",
            ),
        ]
    ])


def match_team_keyboard(match_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Radiant", callback_data=f"mteam:{match_id}:r"),
            InlineKeyboardButton(text="Dire", callback_data=f"mteam:{match_id}:d"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"mb:{match_id}"),
        ],
    ])


def match_players_keyboard(match_id: int, match_data: dict, team: str) -> InlineKeyboardMarkup:
    is_radiant = team == "r"

    players = [
        p for p in match_data.get("players", [])
        if bool(p.get("isRadiant")) == is_radiant and p.get("account_id")
    ]

    rows = []

    for p in players[:5]:
        account_id = int(p.get("account_id"))
        name = short_player_name(p.get("personaname") or f"ID {account_id}")

        rows.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"mp:{match_id}:{account_id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"mplayers:{match_id}",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_match_message(target, match_id: int):
    msg = await target.answer("⏳ Завантажую матч...")

    match_data, hero_map = await asyncio.gather(
        get_match(match_id),
        load_heroes(),
    )

    if not match_data:
        await msg.edit_text("❌ Матч не знайдено. Перевір ID.", parse_mode="HTML")
        return

    await msg.edit_text(
        format_match(match_data, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=match_keyboard(match_id),
    )


async def edit_to_match(call: CallbackQuery, match_id: int):
    match_data, hero_map = await asyncio.gather(
        get_match(match_id),
        load_heroes(),
    )

    if not match_data:
        await call.message.edit_text("❌ Матч не знайдено.", parse_mode="HTML")
        return

    await call.message.edit_text(
        format_match(match_data, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=match_keyboard(match_id),
    )


async def edit_to_player_stats(call: CallbackQuery, account_id: int, match_id: int | None = None):
    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await call.message.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    await call.message.edit_text(
        format_player_stats(player, wl or {}),
        parse_mode="HTML",
        reply_markup=stats_keyboard(account_id, match_id),
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Шукати гравця", callback_data="prompt_player"),
            InlineKeyboardButton(text="🎮 Шукати матч", callback_data="prompt_match"),
        ]
    ])

    await message.answer(
        f'<tg-emoji emoji-id="5321247751399316518">⚛️</tg-emoji> <b>Amaterasu Esports Stats</b>\n'
        f"━━━━━━━━━━━━━━━\n"
        f"Статистика Dota 2 прямо в Telegram\n\n"
        f"📌 <b>Команди:</b>\n"
        f"/start — головне меню\n"
        f"/stats <code>ID</code> — статистика гравця\n"
        f"/match <code>ID</code> — деталі конкретного матчу\n"
        f"/search <code>нікнейм</code> — пошук гравця\n\n"
        f"💡 Сигнатурні герої та останні матчі доступні зі сторінки гравця",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await state.clear()

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("👤 Введіть ID або Nickname гравця:")
        await state.set_state(SearchState.waiting_for_stats)
        return

    query = args[1].strip()

    if not query.isdigit():
        await message.answer(ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(query)
    msg = await message.answer("⏳ Завантажую...")

    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await msg.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    await msg.edit_text(
        format_player_stats(player, wl or {}),
        parse_mode="HTML",
        reply_markup=stats_keyboard(account_id),
    )


@router.message(Command("heroes"))
async def cmd_heroes(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(args[1].strip())
    msg = await message.answer("⏳ Завантажую...")

    heroes, hero_map = await asyncio.gather(
        get_player_heroes(account_id),
        load_heroes(),
    )

    if not heroes or all(h.get("games", 0) == 0 for h in heroes):
        await msg.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id),
        )
        return

    await msg.edit_text(
        format_heroes(heroes, hero_map),
        parse_mode="HTML",
        reply_markup=back_keyboard(account_id),
    )


@router.message(Command("matches"))
async def cmd_matches(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(args[1].strip())
    msg = await message.answer("⏳ Завантажую...")

    matches, hero_map = await asyncio.gather(
        get_recent_matches(account_id),
        load_heroes(),
    )

    if not matches:
        await msg.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id),
        )
        return

    await msg.edit_text(
        format_matches(matches, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=back_keyboard(account_id),
    )


@router.message(Command("search"))
async def cmd_search(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "⚠️ Вкажи нікнейм:\n<code>/search Miracle</code>",
            parse_mode="HTML",
        )
        return

    query = args[1].strip()

    msg = await message.answer(
        f"🔍 Шукаю <b>{escape(query)}</b>...",
        parse_mode="HTML",
    )

    results = await search_player_fast(query)

    if not results:
        await msg.edit_text(ERR_NO_RESULTS, parse_mode="HTML")
        return

    await msg.edit_text(
        format_search(results),
        parse_mode="HTML",
    )


@router.message(Command("match"))
async def cmd_match(message: Message, state: FSMContext):
    await state.clear()

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("🎮 Введіть ID матчу:")
        await state.set_state(SearchState.waiting_for_match)
        return

    if not args[1].strip().isdigit():
        await message.answer(
            "⚠️ Вкажи ID матчу:\n<code>/match 8863808680</code>",
            parse_mode="HTML",
        )
        return

    await render_match_message(message, int(args[1].strip()))


@router.callback_query(F.data == "prompt_player")
async def cb_prompt_player(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("👤 Введіть ID або Nickname гравця:")
    await state.set_state(SearchState.waiting_for_query)


@router.callback_query(F.data == "prompt_match")
async def cb_prompt_match(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("🎮 Введіть ID матчу:")
    await state.set_state(SearchState.waiting_for_match)


@router.message(SearchState.waiting_for_query)
async def handle_player_query(message: Message, state: FSMContext):
    query = message.text.strip()

    if query.startswith("/"):
        return

    await state.clear()

    if query.isdigit():
        account_id = int(query)
        msg = await message.answer("⏳ Завантажую...")

        player, wl = await get_cached_stats(account_id)

        if not player or "profile" not in player:
            await msg.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
            return

        await msg.edit_text(
            format_player_stats(player, wl or {}),
            parse_mode="HTML",
            reply_markup=stats_keyboard(account_id),
        )
        return

    msg = await message.answer(
        f"🔍 Шукаю <b>{escape(query)}</b>...",
        parse_mode="HTML",
    )

    results = await search_player_fast(query)

    if not results:
        await msg.edit_text(ERR_NO_RESULTS, parse_mode="HTML")
        return

    await msg.edit_text(
        format_search(results),
        parse_mode="HTML",
    )


@router.message(SearchState.waiting_for_stats)
async def handle_stats_query(message: Message, state: FSMContext):
    await handle_player_query(message, state)


@router.message(SearchState.waiting_for_match)
async def handle_match_query(message: Message, state: FSMContext):
    query = message.text.strip()

    if query.startswith("/"):
        return

    await state.clear()

    if not query.isdigit():
        await message.answer("⚠️ ID матчу має бути числом", parse_mode="HTML")
        return

    await render_match_message(message, int(query))


@router.callback_query(F.data.startswith("mplayers:"))
async def cb_match_players_menu(call: CallbackQuery):
    match_id = int(call.data.split(":")[1])
    await call.answer()

    await call.message.edit_reply_markup(
        reply_markup=match_team_keyboard(match_id),
    )


@router.callback_query(F.data.startswith("mteam:"))
async def cb_match_team(call: CallbackQuery):
    _, match_id_str, team = call.data.split(":")
    match_id = int(match_id_str)

    await call.answer()

    match_data = await get_match(match_id)

    if not match_data:
        await call.message.edit_text("❌ Матч не знайдено.", parse_mode="HTML")
        return

    await call.message.edit_reply_markup(
        reply_markup=match_players_keyboard(match_id, match_data, team),
    )


@router.callback_query(F.data.startswith("mb:"))
async def cb_back_to_match(call: CallbackQuery):
    match_id = int(call.data.split(":")[1])
    await call.answer()
    await edit_to_match(call, match_id)


@router.callback_query(F.data.startswith("mp:"))
async def cb_match_player_stats(call: CallbackQuery):
    _, match_id_str, account_id_str = call.data.split(":")
    match_id = int(match_id_str)
    account_id = int(account_id_str)

    await call.answer()
    await edit_to_player_stats(call, account_id, match_id)


@router.callback_query(F.data.startswith("mh:"))
async def cb_match_player_heroes(call: CallbackQuery):
    _, match_id_str, account_id_str = call.data.split(":")
    match_id = int(match_id_str)
    account_id = int(account_id_str)

    await call.answer()

    heroes, hero_map = await asyncio.gather(
        get_player_heroes(account_id),
        load_heroes(),
    )

    if not heroes or all(h.get("games", 0) == 0 for h in heroes):
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_to_player_keyboard(match_id, account_id),
        )
        return

    await call.message.edit_text(
        format_heroes(heroes, hero_map),
        parse_mode="HTML",
        reply_markup=back_to_player_keyboard(match_id, account_id),
    )


@router.callback_query(F.data.startswith("mm:"))
async def cb_match_player_matches(call: CallbackQuery):
    _, match_id_str, account_id_str = call.data.split(":")
    match_id = int(match_id_str)
    account_id = int(account_id_str)

    await call.answer()

    matches, hero_map = await asyncio.gather(
        get_recent_matches(account_id),
        load_heroes(),
    )

    if not matches:
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_to_player_keyboard(match_id, account_id),
        )
        return

    await call.message.edit_text(
        format_matches(matches, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=back_to_player_keyboard(match_id, account_id),
    )


@router.callback_query(F.data.startswith("heroes:"))
async def cb_heroes(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    heroes, hero_map = await asyncio.gather(
        get_player_heroes(account_id),
        load_heroes(),
    )

    if not heroes or all(h.get("games", 0) == 0 for h in heroes):
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id),
        )
        return

    await call.message.edit_text(
        format_heroes(heroes, hero_map),
        parse_mode="HTML",
        reply_markup=back_keyboard(account_id),
    )


@router.callback_query(F.data.startswith("matches:"))
async def cb_matches(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    matches, hero_map = await asyncio.gather(
        get_recent_matches(account_id),
        load_heroes(),
    )

    if not matches:
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id),
        )
        return

    await call.message.edit_text(
        format_matches(matches, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=back_keyboard(account_id),
    )


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()
    await edit_to_player_stats(call, account_id)