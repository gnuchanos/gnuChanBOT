"""Read-only DB aggregates for admin dashboards."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import Client, FollowHistory, RedemptionRequest, User


@dataclass(frozen=True)
class DashboardStats:
    users_total: int
    users_with_roblox: int
    total_user_points: int
    clients_total: int
    clients_active: int
    redemptions_pending: int
    pending_redemption_points: int
    redemptions_approved_count: int
    approved_redemption_points_total: int
    redemptions_rejected_count: int
    rejected_redemption_points_total: int
    follow_history_rows: int
    follow_history_rewarded_rows: int
    roblox_collision_groups: int


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def dashboard(self) -> DashboardStats:
        u_total = int(
            (await self._session.execute(select(func.count()).select_from(User))).scalar_one()
        )
        u_rbx = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(User).where(User.roblox_id.is_not(None))
                )
            ).scalar_one()
        )
        total_pts = int(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(User.points), 0)).select_from(User)
                )
            ).scalar_one()
        )
        c_total = int(
            (await self._session.execute(select(func.count()).select_from(Client))).scalar_one()
        )
        c_active = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(Client).where(Client.active.is_(True))
                )
            ).scalar_one()
        )
        r_pend = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "pending")
                )
            ).scalar_one()
        )
        r_pend_pts = int(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(RedemptionRequest.points), 0))
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "pending")
                )
            ).scalar_one()
        )
        r_appr_pts = int(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(RedemptionRequest.points), 0))
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "approved")
                )
            ).scalar_one()
        )
        r_appr_cnt = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "approved")
                )
            ).scalar_one()
        )
        r_rej_pts = int(
            (
                await self._session.execute(
                    select(func.coalesce(func.sum(RedemptionRequest.points), 0))
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "rejected")
                )
            ).scalar_one()
        )
        r_rej_cnt = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(RedemptionRequest)
                    .where(RedemptionRequest.status == "rejected")
                )
            ).scalar_one()
        )
        fh_rows = int(
            (await self._session.execute(select(func.count()).select_from(FollowHistory))).scalar_one()
        )
        fh_rewarded = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(FollowHistory)
                    .where(FollowHistory.rewarded.is_(True))
                )
            ).scalar_one()
        )
        dup_sub = (
            select(User.roblox_id)
            .where(User.roblox_id.is_not(None))
            .group_by(User.roblox_id)
            .having(func.count(User.id) > 1)
            .subquery()
        )
        rbx_collisions = int(
            (await self._session.execute(select(func.count()).select_from(dup_sub))).scalar_one()
        )
        return DashboardStats(
            users_total=u_total,
            users_with_roblox=u_rbx,
            total_user_points=total_pts,
            clients_total=c_total,
            clients_active=c_active,
            redemptions_pending=r_pend,
            pending_redemption_points=r_pend_pts,
            redemptions_approved_count=r_appr_cnt,
            approved_redemption_points_total=r_appr_pts,
            redemptions_rejected_count=r_rej_cnt,
            rejected_redemption_points_total=r_rej_pts,
            follow_history_rows=fh_rows,
            follow_history_rewarded_rows=fh_rewarded,
            roblox_collision_groups=rbx_collisions,
        )

    async def roblox_collision_details(self, *, max_groups: int = 20) -> list[tuple[int, list[int]]]:
        """
        Roblox user IDs that appear on more than one Discord-linked row.

        Returns up to ``max_groups`` Roblox IDs (ordered), each with sorted Discord snowflakes.
        """

        lim = max(1, min(500, int(max_groups)))
        coll_stmt = (
            select(User.roblox_id)
            .where(User.roblox_id.is_not(None))
            .group_by(User.roblox_id)
            .having(func.count(User.id) > 1)
            .order_by(User.roblox_id)
            .limit(lim)
        )
        rid_rows = (await self._session.execute(coll_stmt)).all()
        ids = [int(r[0]) for r in rid_rows]
        if not ids:
            return []
        stmt = select(User).where(User.roblox_id.in_(ids)).order_by(User.roblox_id, User.id)
        users = list((await self._session.execute(stmt)).scalars().all())
        bucket: dict[int, list[int]] = defaultdict(list)
        for u in users:
            if u.roblox_id is None:
                continue
            bucket[int(u.roblox_id)].append(int(u.discord_id))
        return sorted((rid, sorted(dids)) for rid, dids in bucket.items())
