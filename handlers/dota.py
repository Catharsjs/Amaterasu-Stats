import asyncio
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from services.opendota import (
    get_player, get_player_wl, get_player_heroes,
    get_recent_matches, search_player, get_heroes
)
from utils.formatters import format_player_stats, format_heroes, format_matches, format_search
from config import ERR_INVALID_ID, ERR_PLAYER_NOT_FOUND, ERR_API_UNAVAILABLE, ERR_NO_RESULTS, BRAND_EMOJI, BRAND_NAME

router = Router()
_hero_map: dict = {}
_stats_cache: dict = {}
CACHE_TTL = 600  # 10 хвилин


async def load_heroes() -> dict:
    global _hero_map
    if not _hero_map:
        heroes = await get_heroes()
        if heroes:
            _hero_map = {h["id"]: h["localized_name"] for h in heroes}
    return _hero_map


async def get_cached_stats(account_id: int):
    now = time.time()
    if account_id in _stats_cache:
        cached, ts = _stats_cache[account_id]
        if now - ts < CACHE_TTL:
            return cached

    player, wl = await asyncio.gather(
        get_player(account_id),
        get_player_wl(account_id),
    )

    result = (player, wl)
    _stats_cache[account_id] = (result, now)
    return result


def is_private(wl: dict) -> bool:
    return wl.get("win", 0) + wl.get("lose", 0) == 0


PRIVATE_MSG = (
    f"ℹ️ <i>Інформація недоступна — гравець вимкнув поширення історії матчів</i>"
)


def stats_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Сигнатурні герої", callback_data=f"heroes:{account_id}"),
        InlineKeyboardButton(text="Останні матчі", callback_data=f"matches:{account_id}"),
    ]])


def back_keyboard(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Повернутись", callback_data=f"stats:{account_id}"),
    ]])


# /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>Amaterasu Esports Stats</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "Статистика Dota 2 прямо в Telegram\n\n"
        "📌 <b>Команди:</b>\n"
        "/stats <code>ID</code> — статистика гравця\n"
        "/heroes <code>ID</code> — сигнатурні герої\n"
        "/matches <code>ID</code> — останні матчі\n"
        "/search <code>нікнейм</code> — пошук гравця\n\n"
        "💡 Не знаєш свій ID? Використай /search",
        parse_mode="HTML"
    )


# /stats
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(args[1].strip())
    msg = await message.answer("⏳ Завантажую...")

    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await msg.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    text = format_player_stats(player, wl or {})
    await msg.edit_text(text, parse_mode="HTML", reply_markup=stats_keyboard(account_id))


# /heroes
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
        load_heroes()
    )

    if not heroes or all(h.get("games", 0) == 0 for h in heroes):
        await msg.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id)
        )
        return

    await msg.edit_text(
        format_heroes(heroes, hero_map),
        parse_mode="HTML",
        reply_markup=back_keyboard(account_id)
    )


# /matches
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
        load_heroes()
    )

    if not matches:
        await msg.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id)
        )
        return

    await msg.edit_text(
        format_matches(matches, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=back_keyboard(account_id)
    )


# /search
@router.message(Command("search"))
async def cmd_search(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "⚠️ Вкажи нікнейм:\n<code>/search Miracle</code>",
            parse_mode="HTML"
        )
        return

    query = args[1].strip()
    msg = await message.answer(f"🔍 Шукаю <b>{query}</b>...", parse_mode="HTML")

    results = await search_player(query)

    if not results:
        await msg.edit_text(ERR_NO_RESULTS, parse_mode="HTML")
        return

    await msg.edit_text(format_search(results), parse_mode="HTML")


# Inline — сигнатурні герої
@router.callback_query(F.data.startswith("heroes:"))
async def cb_heroes(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    heroes, hero_map = await asyncio.gather(
        get_player_heroes(account_id),
        load_heroes()
    )

    if not heroes or all(h.get("games", 0) == 0 for h in heroes):
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id)
        )
        return

    await call.message.edit_text(
        format_heroes(heroes, hero_map),
        parse_mode="HTML",
        reply_markup=back_keyboard(account_id)
    )


# Inline — останні матчі
@router.callback_query(F.data.startswith("matches:"))
async def cb_matches(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    matches, hero_map = await asyncio.gather(
        get_recent_matches(account_id),
        load_heroes()
    )

    if not matches:
        await call.message.edit_text(
            f"{PRIVATE_MSG}\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard(account_id)
        )
        return

    await call.message.edit_text(
        format_matches(matches, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=back_keyboard(account_id)
    )


# Inline — повернутись до статистики
@router.callback_query(F.data.startswith("stats:"))
async def cb_stats(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await call.message.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    await call.message.edit_text(
        format_player_stats(player, wl or {}),
        parse_mode="HTML",
        reply_markup=stats_keyboard(account_id)
    )