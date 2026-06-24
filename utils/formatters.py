from collections import Counter
from config import (
    BRAND_EMOJI, BRAND_NAME,
    DOTA_LOGO, SHIELD_EMOJI, MEDAL_MAP,
    MAX_HEROES, MAX_MATCHES, HERO_EMOJI
)

ROLE_MAP = {
    1: ('<tg-emoji emoji-id="5332679872009484448">🗡</tg-emoji>', "Carry"),
    2: ('<tg-emoji emoji-id="5334799614463718299">🏹</tg-emoji>', "Midlane"),
    3: ('<tg-emoji emoji-id="5334872418454354241">🛡</tg-emoji>', "Offlane"),
    4: ('<tg-emoji emoji-id="5332641109929642294">🔥</tg-emoji>', "Support"),
    5: ('<tg-emoji emoji-id="5332768606033821927">✨</tg-emoji>', "Hardsupport"),
}


def get_medal(rank_tier: int | None) -> str:
    if rank_tier is None:
        return "Uncalibrated"

    tier = rank_tier // 10
    stars = rank_tier % 10

    if tier not in MEDAL_MAP:
        return "Невідомо"

    name, emoji_id = MEDAL_MAP[tier]

    if emoji_id is None:
        return name

    if tier == 8:
        if stars <= 10:
            emoji_id = "5195215174503505693"
        elif stars <= 100:
            emoji_id = "5194917400125907991"

    medal_emoji = f'<tg-emoji emoji-id="{emoji_id}">🏆</tg-emoji>'
    stars_str = "★" * stars if stars and tier < 8 else ""
    return f"{medal_emoji} {name} {stars_str}".strip()


def get_main_role(matches: list) -> str:
    if not matches:
        return "Невідомо"

    role_counter = Counter()
    for m in matches:
        lane = m.get("lane")
        is_roaming = m.get("is_roaming")

        if is_roaming:
            role_counter[4] += 1
        elif lane == 1:
            role_counter[1] += 1
        elif lane == 2:
            role_counter[2] += 1
        elif lane == 3:
            role_counter[3] += 1
        elif lane == 4:
            role_counter[5] += 1

    if not role_counter:
        return "Невідомо"

    most_common = role_counter.most_common(1)[0][0]
    emoji, name = ROLE_MAP.get(most_common, ("🎮", "Невідомо"))
    return f"{emoji} {name}"


def format_player_stats(profile: dict, wl: dict) -> str:
    name = profile.get("profile", {}).get("personaname", "Невідомо")
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


def wr_emoji(wr: float) -> str:
    if wr < 45:
        return "🔴"
    elif wr < 50:
        return "🟠"
    elif wr < 55:
        return "🟢"
    else:
        return "🟣"

def get_hero_emoji(name: str) -> str:
    emoji_id = HERO_EMOJI.get(name)
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">🎮</tg-emoji>'
    return "🎮"

def format_heroes(heroes: list, hero_map: dict) -> str:
    heroes = [h for h in heroes if h.get("games", 0) > 0]
    if not heroes:
        return (
            f"<i>Інформація недоступна — гравець вимкнув поширення історії матчів</i>\n\n"
            f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
        )
    lines = ["<b>Сигнатурні герої:</b>\n━━━━━━━━━━━━━━━"]
    for h in heroes[:MAX_HEROES]:
        name = hero_map.get(h.get("hero_id"), "Невідомо")
        games = h.get("games", 0)
        wins = h.get("win", 0)
        wr = round(wins / games * 100, 1) if games else 0
        indicator = wr_emoji(wr)

        # вирівнювання: назва до 16 символів, ігри до 4 символів
        name_padded = name[:16].ljust(17)
        games_padded = str(games).rjust(4)

        lines.append(
    f"{get_hero_emoji(name)} <code>{name_padded}{games_padded} матчів  {indicator}{wr:5.1f}%</code>"
)
    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"


def format_matches(matches: list, hero_map: dict) -> str:
    lines = ["<b>Останні матчі:</b>\n━━━━━━━━━━━━━━━"]
    for m in matches[:MAX_MATCHES]:
        hero = hero_map.get(m.get("hero_id"), "Невідомо")
        won = m.get("radiant_win") == (m.get("player_slot", 0) < 128)
        result = "✅" if won else "❌"
        kda = f"{m.get('kills', 0)}/{m.get('deaths', 0)}/{m.get('assists', 0)}"
        mins = m.get("duration", 0) // 60
        match_id = m.get("match_id")

        hero_padded = hero[:14].ljust(15)
        kda_padded = kda.ljust(9)
        mins_padded = f"{mins}хв".rjust(4)

        lines.append(
    f"{result} {get_hero_emoji(hero)} <code>{hero[:14].ljust(15)}{kda.ljust(9)}{mins}хв</code>  "
    f"<a href='https://www.opendota.com/matches/{match_id}'>{match_id}</a>"
)
    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"


def format_search(results: list) -> str:
    lines = ["<b>Результати пошуку:</b>\n━━━━━━━━━━━━━━━"]
    for p in results[:5]:
        name = p.get("personaname", "Невідомо")
        account_id = p.get("account_id")
        similarity = round(p.get("similarity", 0) * 100)
        lines.append(
            f"👤 <b>{name}</b>\n"
            f"🆔 <code>{account_id}</code> | {similarity}% збіг"
        )
    return "\n\n".join(lines) + f"\n\n{BRAND_EMOJI} <b>{BRAND_NAME}</b>"