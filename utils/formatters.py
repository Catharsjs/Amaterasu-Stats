from html import escape

from config import (
    BRAND_EMOJI,
    BRAND_NAME,
    DOTA_LOGO,
    MEDAL_MAP,
    MAX_HEROES,
    MAX_MATCHES,
    HERO_EMOJI,
)


HERO_COL = 21
HERO_NAME_MAX = 20


def code_cell(value: str, width: int) -> str:
    value = str(value or "")
    value = value[:width]
    return escape(value.ljust(width))


def get_medal(rank_tier: int | None) -> str:
    if rank_tier is None:
        return f"{UNCALIBRATED_EMOJI} Uncalibrated"

    tier = rank_tier // 10
    stars = rank_tier % 10

    if tier not in MEDAL_MAP:
        return f"{UNCALIBRATED_EMOJI} Uncalibrated"

    name, emoji_id = MEDAL_MAP[tier]

    if emoji_id is None:
        return f"{UNCALIBRATED_EMOJI} {name}"

    if tier == 8:
        if stars <= 10:
            emoji_id = "5195215174503505693"
        elif stars <= 100:
            emoji_id = "5194917400125907991"

    medal_emoji = f'<tg-emoji emoji-id="{emoji_id}">🏆</tg-emoji>'
    return f"{medal_emoji} {name}".strip()


def get_rank_emoji(rank_tier: int | None) -> str:
    if rank_tier is None:
        return UNCALIBRATED_EMOJI

    tier = rank_tier // 10
    stars = rank_tier % 10

    if tier not in MEDAL_MAP:
        return UNCALIBRATED_EMOJI

    name, emoji_id = MEDAL_MAP[tier]

    if emoji_id is None:
        return UNCALIBRATED_EMOJI

    if tier == 8:
        if stars <= 10:
            emoji_id = "5195215174503505693"
        elif stars <= 100:
            emoji_id = "5194917400125907991"

    return f'<tg-emoji emoji-id="{emoji_id}">🏆</tg-emoji>'


def wr_emoji(wr: float) -> str:
    if wr < 45:
        return "🔴"
    if wr < 50:
        return "🟠"
    if wr < 55:
        return "🟢"
    return "🟣"


def get_hero_emoji(name: str) -> str:
    emoji_id = HERO_EMOJI.get(name)

    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">🎮</tg-emoji>'

    return "🎮"


def hero_display_name(hero_name: str) -> str:
    return str(hero_name or "Невідомо")[:HERO_NAME_MAX]


GOLD_EMOJI = '<tg-emoji emoji-id="5364344020183037021">💰</tg-emoji> '
UNCALIBRATED_EMOJI = '<tg-emoji emoji-id="5325699485001619101">🎖</tg-emoji>'

def format_match(match: dict, hero_map: dict) -> str:
    radiant_win = match.get("radiant_win", False)
    duration = match.get("duration", 0)
    mins = duration // 60
    secs = duration % 60
    match_id = match.get("match_id")
    radiant_score = match.get("radiant_score", 0)
    dire_score = match.get("dire_score", 0)

    radiant_players = [p for p in match.get("players", []) if p.get("isRadiant")]
    dire_players = [p for p in match.get("players", []) if not p.get("isRadiant")]

    def format_player(p: dict) -> str:
        name = p.get("personaname") or "Player"
        hero_id = p.get("hero_id")
        hero_name = hero_map.get(hero_id, "Unknown")
        hero_e = get_hero_emoji(hero_name)
        rank = get_rank_emoji(p.get("rank_tier"))

        k = p.get("kills", 0)
        d = p.get("deaths", 0)
        a = p.get("assists", 0)
        nw = p.get("net_worth", 0)

        name_padded = code_cell(name, 15)
        kda = escape(f"{k}/{d}/{a}".ljust(9))
        nw_str = escape(f"{nw:,}")

        return (
            f"{rank} {hero_e} "
            f"<code>{name_padded}{kda}</code>"
            f"{GOLD_EMOJI}<code>{nw_str}</code>"
        )

    radiant_label = "Radiant 🏆 Перемога" if radiant_win else "Radiant"
    dire_label = "Dire 🏆 Перемога" if not radiant_win else "Dire"

    radiant_lines = "\n".join(format_player(p) for p in radiant_players)
    dire_lines = "\n".join(format_player(p) for p in dire_players)

    return (
        f"<b>Рахунок:</b> {radiant_score} : {dire_score}\n"
        f"<b>Тривалість:</b> {mins:02d}:{secs:02d}\n"
        f"<b>ID матчу:</b> <code>{match_id}</code>\n"
        f"\n"
        f"<b>{radiant_label}</b>\n"
        f"{radiant_lines}\n"
        f"\n"
        f"<b>{dire_label}</b>\n"
        f"{dire_lines}\n"
        f"\n"
        f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
    )


def format_player_stats(profile: dict, wl: dict) -> str:
    name = escape(profile.get("profile", {}).get("personaname", "Невідомо"))
    rank_tier = profile.get("rank_tier")
    rank = get_medal(rank_tier)
    mmr = profile.get("mmr_estimate", {}).get("estimate")

    wins = wl.get("win", 0)
    losses = wl.get("lose", 0)
    total = wins + losses
    winrate = round(wins / total * 100, 1) if total else 0

    mmr_str = f" ({mmr} MMR)" if mmr else ""

    if total == 0:
        return (
            f"{DOTA_LOGO} <b>{name}</b>\n"
            f"\n"
            f"Ранк: {rank}{mmr_str}\n"
            f"\n"
            f"<i>Інформація недоступна — гравець вимкнув поширення історії матчів</i>\n"
            f"\n"
            f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
        )

    return (
        f"{DOTA_LOGO} <b>{name}</b>\n"
        f"\n"
        f"Ранк: {rank}{mmr_str}\n"
        f"\n"
        f"{total} матчів ({winrate}% Вінрейт)\n"
        f"\n"
        f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
    )


def format_heroes(heroes: list, hero_map: dict) -> str:
    heroes = [h for h in heroes if h.get("games", 0) > 0]

    if not heroes:
        return (
            f"<i>Інформація недоступна — гравець вимкнув поширення історії матчів</i>\n\n"
            f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
        )

    shown_heroes = heroes[:MAX_HEROES]

    names = [
        hero_display_name(hero_map.get(h.get("hero_id"), "Невідомо"))
        for h in shown_heroes
    ]

    hero_width = min(
        max(len(name) for name in names) + 2,
        HERO_COL
    )

    games_width = max(
        len("Матчі"),
        max(len(str(h.get("games", 0))) for h in shown_heroes)
    )

    header = (
        f"      "
        f"<code>{'Герой'.ljust(hero_width)}"
        f"{'Матчі'.rjust(games_width)} "
        f"{'WR'.rjust(6)}</code>"
    )

    lines = [
        "<b>Сигнатурні герої:</b>\n",
        header,
    ]

    for h, name in zip(shown_heroes, names):
        raw_name = hero_map.get(h.get("hero_id"), "Невідомо")

        games = h.get("games", 0)
        wins = h.get("win", 0)
        wr = round(wins / games * 100, 1) if games else 0
        indicator = wr_emoji(wr)

        name_padded = code_cell(name, hero_width)
        games_padded = str(games).rjust(games_width)
        wr_padded = f"{wr:5.1f}%"

        lines.append(
            f"{get_hero_emoji(raw_name)} "
            f"<code>{name_padded}{games_padded} </code>"
            f"{indicator}<code>{wr_padded}</code>"
        )

    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"


def format_matches(matches: list, hero_map: dict) -> str:
    lines = ["<b>Останні матчі:</b>\n"]

    for m in matches[:MAX_MATCHES]:
        raw_hero = hero_map.get(m.get("hero_id"), "Невідомо")
        hero_name = hero_display_name(raw_hero)
        hero_emoji = get_hero_emoji(raw_hero)

        won = m.get("radiant_win") == (m.get("player_slot", 0) < 128)
        result = "✅" if won else "❌"

        kda = f"{m.get('kills', 0)}/{m.get('deaths', 0)}/{m.get('assists', 0)}"
        mins = m.get("duration", 0) // 60
        match_id = m.get("match_id")

        hero_padded = code_cell(hero_name, HERO_COL)
        kda_padded = escape(kda.ljust(9))
        mins_padded = escape(f"{mins}хв".rjust(5))

        lines.append(
            f"{result} {hero_emoji} "
            f"<code>{hero_padded}{kda_padded}{mins_padded}</code>  "
            f'<a href="https://www.opendota.com/matches/{match_id}">{match_id}</a>'
        )

    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"


def format_search(results: list) -> str:
    lines = ["<b>Результати пошуку:</b>\n━━━━━━━━━━━━━━━"]

    for p in results[:5]:
        name = p.get("personaname") or "Невідомо"
        account_id = str(p.get("account_id") or "—")
        rank = get_medal(p.get("rank_tier"))

        name_padded = code_cell(name, 17)
        id_padded = escape(account_id.rjust(10))

        lines.append(
            f"👤 <code>{name_padded}{id_padded}</code>  {rank}"
        )

    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"