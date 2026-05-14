"""Prefix command access helpers."""

from __future__ import annotations

from typing import Any


def prefix_ban_message(bot: Any, discord_user_id: int) -> str | None:
    """
    If the user is in ``DISCORD_BANNED_IDS``, return a short Turkish message; else ``None``.

    Slash komutları ``follow_cog`` içinde ayrıca engellenir; prefix için burada kontrol edilir.
    """

    settings = getattr(bot, "settings", None)
    if settings is None:
        return None
    if discord_user_id in settings.banned_id_set():
        return "Bu botta prefix komutlarını kullanman engellenmiş."
    return None
