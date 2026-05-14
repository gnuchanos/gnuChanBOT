"""Leaderboard queries."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import User


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def top_by_points(self, limit: int = 10) -> list[User]:
        stmt = (
            select(User)
            .where(User.points > 0)
            .order_by(User.points.desc(), User.id.asc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def rank_for_discord_user(self, discord_id: int) -> tuple[int | None, int]:
        """
        ``points > 0`` olanlar arasında 1 tabanlı sıra ve kullanıcının puanı.

        Sıralama ``top_by_points`` ile aynı: önce puan azalan, eşitte ``id`` artan.
        """

        stmt_u = select(User).where(User.discord_id == discord_id).limit(1)
        user = (await self._session.execute(stmt_u)).scalar_one_or_none()
        if user is None:
            return None, 0
        if user.points <= 0:
            return None, int(user.points)

        stmt_rank = (
            select(func.count())
            .select_from(User)
            .where(
                or_(
                    User.points > user.points,
                    and_(User.points == user.points, User.id < user.id),
                )
            )
        )
        ahead = int((await self._session.execute(stmt_rank)).scalar_one())
        return ahead + 1, int(user.points)
