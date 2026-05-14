"""Nakit / ödeme talepleri (kredi düşümü yönetici onayı ile)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import RedemptionRequest, User

logger = logging.getLogger(__name__)


class RedemptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_pending_for_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(RedemptionRequest)
            .where(RedemptionRequest.user_id == user_id, RedemptionRequest.status == "pending")
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def create_request(
        self,
        *,
        discord_id: int,
        points: int,
        note: str | None,
        max_pending_per_user: int,
        max_single_redemption: int,
    ) -> RedemptionRequest:
        if points < 1:
            raise ValueError("Geçersiz miktar.")
        if max_single_redemption > 0 and points > max_single_redemption:
            raise ValueError(f"Tek talepte en fazla **{max_single_redemption}** kredi talep edebilirsin.")

        stmt = select(User).where(User.discord_id == discord_id).limit(1)
        user = (await self._session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise ValueError("Önce `/register` veya `/register_username` ile kayıt ol.")
        if user.points < points:
            raise ValueError(f"Yetersiz bakiye. Mevcut: **{user.points}** kredi.")

        pending = await self.count_pending_for_user(user.id)
        if pending >= max_pending_per_user:
            raise ValueError(
                f"En fazla **{max_pending_per_user}** bekleyen talebin olabilir. "
                "Onay veya ret sonrası yeni talep açabilirsin.",
            )

        clean_note = (note or "").strip()[:240] or None
        row = RedemptionRequest(
            user_id=user.id,
            points=int(points),
            note=clean_note,
            status="pending",
        )
        self._session.add(row)
        await self._session.flush()
        logger.info("Redemption pending id=%s user_pk=%s points=%s", row.id, user.id, points)
        return row

    async def list_by_status(self, status: str | None, limit: int = 25) -> list[tuple[RedemptionRequest, User]]:
        stmt = select(RedemptionRequest, User).join(User).order_by(RedemptionRequest.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(RedemptionRequest.status == status)
        rows = (await self._session.execute(stmt)).all()
        return [(r, u) for r, u in rows]

    async def get_with_user(self, request_id: int) -> tuple[RedemptionRequest, User] | None:
        stmt = (
            select(RedemptionRequest, User)
            .join(User, RedemptionRequest.user_id == User.id)
            .where(RedemptionRequest.id == int(request_id))
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return (row[0], row[1])

    async def resolve(
        self,
        *,
        request_id: int,
        approve: bool,
        resolver_discord_id: int,
        admin_note: str | None,
    ) -> tuple[RedemptionRequest, str]:
        """
        Talebi onayla veya reddet.

        Onayda kullanıcı bakiyesi yeterliyse ``points`` düşülür; değilse talep **reddedilir**.
        """

        req = await self._session.get(RedemptionRequest, request_id)
        if req is None:
            raise ValueError("Talep bulunamadı.")
        if req.status != "pending":
            raise ValueError(f"Talep artık bekleyemez (durum: {req.status}).")

        user = await self._session.get(User, req.user_id)
        if user is None:
            raise ValueError("Kullanıcı kaydı yok.")

        now = datetime.now(timezone.utc)
        note = (admin_note or "").strip()[:240] or None

        if approve:
            if user.points < req.points:
                req.status = "rejected"
                req.resolved_at = now
                req.resolver_discord_id = resolver_discord_id
                req.admin_note = note or f"Onay anında yetersiz bakiye (mevcut: {user.points})."
                msg = "Talep **reddedildi** (yetersiz bakiye)."
            else:
                user.points -= req.points
                req.status = "approved"
                req.resolved_at = now
                req.resolver_discord_id = resolver_discord_id
                req.admin_note = note
                msg = f"Talep **onaylandı**; kullanıcıdan **{req.points}** kredi düşüldü."
                logger.info(
                    "Redemption approved id=%s user_pk=%s points=%s resolver=%s",
                    req.id,
                    user.id,
                    req.points,
                    resolver_discord_id,
                )
        else:
            req.status = "rejected"
            req.resolved_at = now
            req.resolver_discord_id = resolver_discord_id
            req.admin_note = note
            msg = "Talep **reddedildi**; bakiye değişmedi."
            logger.info("Redemption rejected id=%s resolver=%s", req.id, resolver_discord_id)

        return req, msg

    async def pending_count_for_discord(self, discord_id: int) -> int:
        stmt = select(User).where(User.discord_id == discord_id).limit(1)
        user = (await self._session.execute(stmt)).scalar_one_or_none()
        if user is None:
            return 0
        return await self.count_pending_for_user(user.id)

    async def list_for_discord_user(self, discord_id: int, *, limit: int = 10) -> list[RedemptionRequest]:
        """Kullanıcının taleplerini yeniden eskiye."""

        stmt_u = select(User).where(User.discord_id == discord_id).limit(1)
        user = (await self._session.execute(stmt_u)).scalar_one_or_none()
        if user is None:
            return []
        lim = max(1, min(25, int(limit)))
        stmt = (
            select(RedemptionRequest)
            .where(RedemptionRequest.user_id == user.id)
            .order_by(RedemptionRequest.id.desc())
            .limit(lim)
        )
        return list((await self._session.execute(stmt)).scalars().all())
