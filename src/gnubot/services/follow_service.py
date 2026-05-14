"""Follow verification, rewards, and penalties (anti-exploit)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gnubot.models import Client, FollowHistory, User
from gnubot.roblox import RobloxClient
from gnubot.services.user_service import UserService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitionOutcome:
    """Tek (kullanıcı, görev) senkron sonucu. ``code``: rewarded | penalized | synced_following_no_credit | already_rewarded | not_following | rewarded_unfollowed."""

    points_delta: int
    code: str


@dataclass(frozen=True)
class CheckRunResult:
    """``/check`` sonucu; ``error`` doluysa ``rows`` boş olabilir."""

    user: User | None
    rows: list[tuple[Client, TransitionOutcome]]
    error: str | None = None


class FollowService:
    """
    Takip durumu ve kredi (puan) mantığı.

    * Aynı (kullanıcı, müşteri) için **en fazla bir kez** pozitif kredi: ``FollowHistory.rewarded``.
    * **Yeni kredi** varsayılan olarak yalnızca ``/check`` ile verilir (``allow_new_reward=True``).
    * Arka plan döngüsü takip durumunu senkronlar ve takipten çıkış **cezasını** uygular.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _active_clients(self) -> list[Client]:
        stmt = select(Client).where(Client.active.is_(True)).order_by(Client.id.asc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def _users_with_roblox(self) -> list[User]:
        stmt = select(User).where(User.roblox_id.is_not(None)).order_by(User.id.asc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_or_create_history(self, user_id: int, client_id: int) -> FollowHistory:
        stmt = select(FollowHistory).where(
            FollowHistory.user_id == user_id,
            FollowHistory.client_id == client_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = FollowHistory(
                user_id=user_id,
                client_id=client_id,
                rewarded=False,
                currently_following=False,
            )
            self._session.add(row)
            await self._session.flush()
        return row

    async def apply_transition(
        self,
        *,
        user: User,
        client: Client,
        now_following: bool,
        reward_points: int,
        penalty_points: int,
        allow_new_reward: bool,
    ) -> TransitionOutcome:
        hist = await self.get_or_create_history(user.id, client.id)
        was = bool(hist.currently_following)

        if hist.rewarded and was and not now_following:
            user.points = max(0, user.points - penalty_points)
            hist.currently_following = False
            logger.info(
                "Penalty -%s: discord=%s user_pk=%s client=%s target=%s",
                penalty_points,
                user.discord_id,
                user.id,
                client.id,
                client.roblox_target_id,
            )
            return TransitionOutcome(-penalty_points, "penalized")

        if not hist.rewarded and now_following:
            if allow_new_reward:
                user.points += reward_points
                hist.rewarded = True
                hist.rewarded_at = datetime.now(timezone.utc)
                hist.currently_following = True
                logger.info(
                    "Reward +%s: discord=%s user_pk=%s client=%s target=%s",
                    reward_points,
                    user.discord_id,
                    user.id,
                    client.id,
                    client.roblox_target_id,
                )
                return TransitionOutcome(reward_points, "rewarded")
            hist.currently_following = True
            if not was:
                logger.debug(
                    "Scheduler: following without credit yet user=%s client=%s",
                    user.id,
                    client.id,
                )
            return TransitionOutcome(0, "synced_following_no_credit")

        if hist.rewarded and now_following:
            hist.currently_following = True
            return TransitionOutcome(0, "already_rewarded")

        hist.currently_following = False
        if not hist.rewarded:
            return TransitionOutcome(0, "not_following")
        return TransitionOutcome(0, "rewarded_unfollowed")

    async def sync_all_users(
        self,
        roblox: RobloxClient,
        *,
        reward_points: int,
        penalty_points: int,
    ) -> int:
        """
        Tüm Roblox bağlı kullanıcılar için takip setini çek; **yeni kredi verme**,
        sadece durum + ceza senkronu (kredi ``/check`` ile).
        """

        clients = await self._active_clients()
        if not clients:
            return 0
        users = await self._users_with_roblox()
        processed = 0
        user_svc = UserService(self._session)
        for user in users:
            rid = user.roblox_id
            if rid is None:
                continue
            try:
                following = await roblox.iter_following_ids(int(rid))
            except Exception:
                logger.exception("Failed to load followings for roblox_id=%s", rid)
                continue
            for client in clients:
                now = int(client.roblox_target_id) in following
                await self.apply_transition(
                    user=user,
                    client=client,
                    now_following=now,
                    reward_points=reward_points,
                    penalty_points=penalty_points,
                    allow_new_reward=False,
                )
            await user_svc.recompute_aggregates(user.id)
            processed += 1
        return processed

    async def run_check_for_discord_user(
        self,
        roblox: RobloxClient,
        discord_id: int,
        *,
        reward_points: int,
        penalty_points: int,
        client_id: int | None = None,
    ) -> CheckRunResult:
        """
        Tek kullanıcı için Roblox takip listesini çek; aktif görevlerde kredi / ceza / durum güncelle.

        ``client_id`` verilirse yalnızca bu görev (aktifse) işlenir.
        """

        user_svc = UserService(self._session)
        user = await user_svc.get_by_discord_id(discord_id)
        if user is None:
            return CheckRunResult(user=None, rows=[], error="no_user")
        if user.roblox_id is None:
            return CheckRunResult(user=user, rows=[], error="no_roblox")

        clients = await self._active_clients()
        if client_id is not None:
            match = [c for c in clients if c.id == int(client_id)]
            if not match:
                c_any = await self._session.get(Client, int(client_id))
                if c_any is None:
                    return CheckRunResult(user=user, rows=[], error="client_not_found")
                return CheckRunResult(user=user, rows=[], error="client_inactive")
            clients = match

        if not clients:
            return CheckRunResult(user=user, rows=[], error="no_active_tasks")

        try:
            following = await roblox.iter_following_ids(int(user.roblox_id))
        except Exception:
            logger.exception("check: followings failed discord_id=%s", discord_id)
            raise

        rows: list[tuple[Client, TransitionOutcome]] = []
        for client in clients:
            now = int(client.roblox_target_id) in following
            out = await self.apply_transition(
                user=user,
                client=client,
                now_following=now,
                reward_points=reward_points,
                penalty_points=penalty_points,
                allow_new_reward=True,
            )
            rows.append((client, out))

        await user_svc.recompute_aggregates(user.id)
        await self._session.refresh(user)
        return CheckRunResult(user=user, rows=rows, error=None)
