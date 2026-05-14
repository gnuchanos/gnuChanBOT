"""
gnuChanBOT — Discord entrypoint (Roblox follow-task system).

Run from this folder::

    python gnuchanos_bot.py

Ensure ``.env`` exists (see ``.env.example`` in the repository root). Working
directory should be ``src`` so imports resolve, or extend ``PYTHONPATH``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


async def _amain() -> None:
    from gnubot.bot_app import GnuChanBot
    from gnubot.config.settings import get_settings
    from gnubot.infrastructure.database import create_engine, init_schema, make_session_factory
    from gnubot.infrastructure.logging_config import configure_logging
    from gnubot.infrastructure.paths import ensure_sqlite_parent_dir
    from gnubot.roblox import RobloxClient

    settings = get_settings()
    configure_logging(settings.log_level)
    ensure_sqlite_parent_dir(settings.database_url)

    engine = create_engine(settings.database_url)
    await init_schema(engine)
    session_maker = make_session_factory(engine)

    roblox = RobloxClient(
        timeout_seconds=settings.roblox_http_timeout_seconds,
        max_retries=settings.roblox_max_retries,
        cache_ttl_seconds=settings.roblox_cache_ttl_seconds,
    )

    bot = GnuChanBot(
        settings=settings,
        engine=engine,
        session_factory=session_maker,
        roblox=roblox,
    )

    async with bot:
        await bot.start(settings.discord_token)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
