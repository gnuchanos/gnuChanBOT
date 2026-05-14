"""Client (campaign) CRUD and Roblox follower sync."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import Client
from gnubot.roblox import RobloxClient

logger = logging.getLogger(__name__)


def _apply_roblox_follower_count(client: Client, count: int) -> None:
    """Set ``current_followers`` from Roblox and derive ``active`` (goal not yet reached)."""

    client.current_followers = int(count)
    should_active = int(count) < int(client.target_followers)
    if not should_active and client.active:
        logger.info(
            "Deactivating client %s (target reached: %s >= %s)",
            client.id,
            count,
            client.target_followers,
        )
    client.active = should_active


class ClientService:
    """Admin-facing client management and status updates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_client(
        self,
        roblox_target_id: int,
        target_followers: int,
        *,
        current_followers: int | None = None,
        display_name: str | None = None,
    ) -> Client:
        c = Client(
            roblox_target_id=roblox_target_id,
            target_followers=target_followers,
            current_followers=current_followers if current_followers is not None else 0,
            active=True,
            display_name=display_name,
        )
        self._session.add(c)
        await self._session.flush()
        return c

    async def list_clients(self, *, active_only: bool = False) -> list[Client]:
        stmt = select(Client).order_by(Client.id.desc())
        if active_only:
            stmt = stmt.where(Client.active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_clients(self, *, active: bool | None = None) -> int:
        """Count clients; ``active`` True/False filters, ``None`` = all."""

        stmt = select(func.count()).select_from(Client)
        if active is True:
            stmt = stmt.where(Client.active.is_(True))
        elif active is False:
            stmt = stmt.where(Client.active.is_(False))
        return int((await self._session.execute(stmt)).scalar_one())

    async def get(self, client_id: int) -> Client | None:
        return await self._session.get(Client, client_id)

    async def set_active(self, client_id: int, active: bool) -> Client | None:
        c = await self.get(client_id)
        if c is None:
            return None
        c.active = active
        return c

    async def set_target_followers(self, client_id: int, target_followers: int) -> Client | None:
        """Update goal and recompute ``active`` from stored ``current_followers``."""

        if target_followers <= 0:
            raise ValueError("Hedef takipçi sayısı pozitif olmalı.")
        c = await self.get(client_id)
        if c is None:
            return None
        c.target_followers = int(target_followers)
        c.active = int(c.current_followers) < int(c.target_followers)
        return c

    async def set_display_name(self, client_id: int, display_name: str | None) -> Client | None:
        c = await self.get(client_id)
        if c is None:
            return None
        clean = (display_name or "").strip()
        c.display_name = clean or None
        return c

    async def refresh_single_follower_count(self, roblox: RobloxClient, client_id: int) -> Client | None:
        """Fetch Roblox follower count for one client and update ``active``."""

        c = await self.get(client_id)
        if c is None:
            return None
        count = await roblox.get_follower_count(int(c.roblox_target_id))
        _apply_roblox_follower_count(c, count)
        return c

    async def refresh_follower_counts(self, roblox: RobloxClient) -> None:
        """Pull follower counts from Roblox and flip ``active`` when goals are met."""

        clients = await self.list_clients(active_only=False)
        for c in clients:
            try:
                count = await roblox.get_follower_count(int(c.roblox_target_id))
            except Exception:
                logger.exception("Failed follower count for client %s", c.id)
                continue
            _apply_roblox_follower_count(c, count)
