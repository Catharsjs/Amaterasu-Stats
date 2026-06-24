import asyncio
import time
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from html import escape

from services.opendota import (
    get_player, get_player_wl, get_player_heroes,
    get_recent_matches, search_player, get_heroes,
    get_match
)
from utils.formatters import format_player_stats, format_heroes, format_matches, format_search, format_match
from config import ERR_INVALID_ID, ERR_PLAYER_NOT_FOUND, ERR_API_UNAVAILABLE, ERR_NO_RESULTS, BRAND_EMOJI, BRAND_NAME

router = Router()
logger = logging.getLogger(__name__)


class SearchState(StatesGroup):
    waiting_for_query = State()
    waiting_for_match = State()
    waiting_for_stats = State()


_hero_map: dict = {}
_stats_cache: dict = {}
CACHE_TTL = 600  # 10 хвилин

# Зберігаємо message_id, які бот/користувач створювали під час роботи з ботом.
# Telegram не дає "очистити весь чат" напряму, тому видаляємо ті повідомлення, які знаємо.
_chat_messages: dict[int, set[int]] = {}


def remember_message(chat_id: int, message_id: int) -> None:
    _chat_messages.setdefault(chat_id, set()).add(message_id)


async def bot_answer(message: Message, *args, **kwargs) -> Message:
    sent = await message.answer(*args, **kwargs)
    remember_message(sent.chat.id, sent.message_id)
    return sent


async def delete_tracked_messages(message: Message) -> None:
    chat_id = message.chat.id

    # Запам'ятовуємо саму команду /clear, щоб теж видалити.
    remember_message(chat_id, message.message_id)

    ids = sorted(_chat_messages.get(chat_id, set()), reverse=True)

    for message_id in ids:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    _chat_messages[chat_id] = set()


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
            logger.info(f"Cache hit for {account_id}")
            return cached

    logger.info(f"Fetching player {account_id}...")
    player = await get_player(account_id)
    logger.info(f"Player done: {account_id}")

    wl = await get_player_wl(account_id)
    logger.info(f"WL done: {account_id}")

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
    remember_message(message.chat.id, message.message_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Шукати гравця", callback_data="prompt_player"),
            InlineKeyboardButton(text="🎮 Шукати матч", callback_data="prompt_match"),
        ]
    ])

    await bot_answer(
        message,
        f'<tg-emoji emoji-id="5321247751399316518">⚛️</tg-emoji> <b>Amaterasu Esports Stats</b>\n'
        f"━━━━━━━━━━━━━━━\n"
        f"Статистика Dota 2 прямо в Telegram\n\n"
        f"📌 <b>Команди:</b>\n"
        f"/stats <code>ID</code> — статистика гравця\n"
        f"/heroes <code>ID</code> — сигнатурні герої\n"
        f"/matches <code>ID</code> — останні матчі\n"
        f"/match <code>ID</code> — деталі конкретного матчу\n"
        f"/search <code>нікнейм</code> — пошук гравця\n"
        f"/clear — очистити чат і повернутись на старт\n\n"
        f"💡 Не знаєш свій ID? Використай /search",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# /clear — ОБОВ'ЯЗКОВО вище FSM-handler'ів
@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext):
    await state.clear()
    await delete_tracked_messages(message)

    # Після очищення запускаємо /start з нуля
    await cmd_start(message)


@router.callback_query(F.data == "prompt_player")
async def cb_prompt_player(call: CallbackQuery, state: FSMContext):
    await call.answer()

    remember_message(call.message.chat.id, call.message.message_id)

    sent = await call.message.answer("👤 Введіть ID або Nickname гравця:")
    remember_message(sent.chat.id, sent.message_id)

    await state.set_state(SearchState.waiting_for_query)


@router.callback_query(F.data == "prompt_match")
async def cb_prompt_match(call: CallbackQuery, state: FSMContext):
    await call.answer()

    remember_message(call.message.chat.id, call.message.message_id)

    sent = await call.message.answer("🎮 Введіть ID матчу:")
    remember_message(sent.chat.id, sent.message_id)

    await state.set_state(SearchState.waiting_for_match)


@router.message(SearchState.waiting_for_query)
async def handle_player_query(message: Message, state: FSMContext):
    remember_message(message.chat.id, message.message_id)

    # Якщо користувач ввів команду під час FSM — не обробляємо її як ID/нік.
    if message.text and message.text.startswith("/"):
        return

    await state.clear()

    query = message.text.strip()

    if query.isdigit():
        msg = await bot_answer(message, "⏳ Завантажую...")

        player, wl = await get_cached_stats(int(query))

        if not player or "profile" not in player:
            await msg.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
            return

        await msg.edit_text(
            format_player_stats(player, wl or {}),
            parse_mode="HTML",
            reply_markup=stats_keyboard(int(query))
        )
    else:
        msg = await bot_answer(
            message,
            f"🔍 Шукаю <b>{escape(query)}</b>...",
            parse_mode="HTML"
        )

        results = await search_player(query)

        if not results:
            await msg.edit_text(ERR_NO_RESULTS, parse_mode="HTML")
            return

        await msg.edit_text(format_search(results), parse_mode="HTML")


@router.message(SearchState.waiting_for_stats)
async def handle_stats_query(message: Message, state: FSMContext):
    await handle_player_query(message, state)


@router.message(SearchState.waiting_for_match)
async def handle_match_query(message: Message, state: FSMContext):
    remember_message(message.chat.id, message.message_id)

    # Якщо користувач ввів команду під час FSM — не обробляємо її як ID матчу.
    if message.text and message.text.startswith("/"):
        return

    await state.clear()

    query = message.text.strip()

    if not query.isdigit():
        await bot_answer(message, "⚠️ ID матчу має бути числом", parse_mode="HTML")
        return

    msg = await bot_answer(message, "⏳ Завантажую матч...")

    match_data, hero_map = await asyncio.gather(
        get_match(int(query)),
        load_heroes()
    )

    if not match_data:
        await msg.edit_text("❌ Матч не знайдено.", parse_mode="HTML")
        return

    await msg.edit_text(
        format_match(match_data, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# /stats
@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    remember_message(message.chat.id, message.message_id)

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await bot_answer(message, "👤 Введіть ID або Nickname гравця:")
        await state.set_state(SearchState.waiting_for_stats)
        return

    account_id_str = args[1].strip()

    if not account_id_str.isdigit():
        await bot_answer(message, ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(account_id_str)
    msg = await bot_answer(message, "⏳ Завантажую...")

    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await msg.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    await msg.edit_text(
        format_player_stats(player, wl or {}),
        parse_mode="HTML",
        reply_markup=stats_keyboard(account_id)
    )


# /heroes
@router.message(Command("heroes"))
async def cmd_heroes(message: Message):
    remember_message(message.chat.id, message.message_id)

    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip().isdigit():
        await bot_answer(message, ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(args[1].strip())
    msg = await bot_answer(message, "⏳ Завантажую...")

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
    remember_message(message.chat.id, message.message_id)

    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip().isdigit():
        await bot_answer(message, ERR_INVALID_ID, parse_mode="HTML")
        return

    account_id = int(args[1].strip())
    msg = await bot_answer(message, "⏳ Завантажую...")

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
    remember_message(message.chat.id, message.message_id)

    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip():
        await bot_answer(
            message,
            "⚠️ Вкажи нікнейм:\n<code>/search Miracle</code>",
            parse_mode="HTML"
        )
        return

    query = args[1].strip()

    msg = await bot_answer(
        message,
        f"🔍 Шукаю <b>{escape(query)}</b>...",
        parse_mode="HTML"
    )

    results = await search_player(query)

    if not results:
        await msg.edit_text(ERR_NO_RESULTS, parse_mode="HTML")
        return

    await msg.edit_text(format_search(results), parse_mode="HTML")


# /match
@router.message(Command("match"))
async def cmd_match(message: Message, state: FSMContext):
    remember_message(message.chat.id, message.message_id)

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await bot_answer(message, "🎮 Введіть ID матчу:")
        await state.set_state(SearchState.waiting_for_match)
        return

    if not args[1].strip().isdigit():
        await bot_answer(
            message,
            "⚠️ Вкажи ID матчу:\n<code>/match 8863808680</code>",
            parse_mode="HTML"
        )
        return

    match_id = int(args[1].strip())
    msg = await bot_answer(message, "⏳ Завантажую матч...")

    match_data, hero_map = await asyncio.gather(
        get_match(match_id),
        load_heroes()
    )

    if not match_data:
        await msg.edit_text("❌ Матч не знайдено. Перевір ID.", parse_mode="HTML")
        return

    await msg.edit_text(
        format_match(match_data, hero_map),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# Inline — сигнатурні герої
@router.callback_query(F.data.startswith("heroes:"))
async def cb_heroes(call: CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await call.answer()

    remember_message(call.message.chat.id, call.message.message_id)

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

    remember_message(call.message.chat.id, call.message.message_id)

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

    remember_message(call.message.chat.id, call.message.message_id)

    player, wl = await get_cached_stats(account_id)

    if not player or "profile" not in player:
        await call.message.edit_text(ERR_PLAYER_NOT_FOUND, parse_mode="HTML")
        return

    await call.message.edit_text(
        format_player_stats(player, wl or {}),
        parse_mode="HTML",
        reply_markup=stats_keyboard(account_id)
    )