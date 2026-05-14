"""Periodic Roblox follow verification."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from gnubot.infrastructure.database import open_session
from gnubot.services.client_service import ClientService
from gnubot.services.follow_service import FollowService

if TYPE_CHECKING:
    from gnubot.bot_app import GnuChanBot

logger = logging.getLogger(__name__)


async def follow_checker_loop(bot: GnuChanBot) -> None:
    """Run follow + follower-count sync on an interval until cancelled."""

    await bot.wait_until_ready()
    while not bot.is_closed():
        interval = int(bot.settings.follow_check_interval_seconds)
        try:
            async with open_session(bot.session_factory) as session:
                clients = ClientService(session)
                await clients.refresh_follower_counts(bot.roblox)
                follows = FollowService(session)
                n = await follows.sync_all_users(
                    bot.roblox,
                    reward_points=bot.settings.follow_reward_points,
                    penalty_points=bot.settings.follow_penalty_points,
                )
                logger.info("Follow check cycle complete (%s users synced).", n)
            asyncio.create_task(bot.refresh_presence(), name="refresh-presence")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Follow check cycle failed")
        try:
            await asyncio.wait_for(asyncio.sleep(max(1, interval)), timeout=max(1, interval))
        except asyncio.CancelledError:
            break
