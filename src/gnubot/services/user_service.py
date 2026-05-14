"""User registration and lookups."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import FollowHistory, User


class UserService:
    """Persistence helpers for Discord users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_discord_id(self, discord_id: int) -> User | None:
        stmt = select(User).where(User.discord_id == discord_id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_roblox_id(self, roblox_id: int) -> User | None:
        stmt = select(User).where(User.roblox_id == int(roblox_id)).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def register_roblox(self, discord_id: int, roblox_id: int) -> User:
        user = await self.get_by_discord_id(discord_id)
        if user is None:
            user = User(discord_id=discord_id, roblox_id=roblox_id, points=0)
            self._session.add(user)
            await self._session.flush()
        else:
            user.roblox_id = roblox_id
        return user

    async def ensure_user(self, discord_id: int) -> User:
        user = await self.get_by_discord_id(discord_id)
        if user is None:
            user = User(discord_id=discord_id, roblox_id=None, points=0)
            self._session.add(user)
            await self._session.flush()
        return user

    async def recompute_aggregates(self, user_id: int) -> None:
        """Refresh denormalized counters from ``follow_history``."""

        from sqlalchemy import func

        from gnubot.models import FollowHistory

        stmt_active = (
            select(func.count())
            .select_from(FollowHistory)
            .where(
                FollowHistory.user_id == user_id,
                FollowHistory.currently_following.is_(True),
            )
        )
        stmt_done = (
            select(func.count())
            .select_from(FollowHistory)
            .where(FollowHistory.user_id == user_id, FollowHistory.rewarded.is_(True))
        )
        user = await self._session.get(User, user_id)
        if user is None:
            return
        active = int((await self._session.execute(stmt_active)).scalar_one())
        done = int((await self._session.execute(stmt_done)).scalar_one())
        user.active_follows = active
        user.completed_follows = done

    async def clear_roblox_link(self, discord_id: int) -> User | None:
        """
        Remove Roblox binding and **delete** ``follow_history`` rows for a clean re-link later.

        Kredi (``points``) ve nakit talepleri korunur.
        """

        user = await self.get_by_discord_id(discord_id)
        if user is None:
            return None
        await self._session.execute(delete(FollowHistory).where(FollowHistory.user_id == user.id))
        user.roblox_id = None
        await self.recompute_aggregates(user.id)
        return user
