"""Async Roblox HTTP client with retries, timeouts, and TTL caching."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class RobloxAPIError(Exception):
    """Raised for unexpected Roblox API responses."""


class RobloxClient:
    """
    Thin wrapper around public Roblox web APIs used by the bot.

    Followings are paginated; follower counts are cached briefly to reduce load.
    """

    USERS_BASE = "https://users.roblox.com"
    FRIENDS_BASE = "https://friends.roblox.com"

    @staticmethod
    def _default_headers() -> dict[str, str]:
        """Identify the bot to Roblox public APIs (best practice for HTTP clients)."""

        try:
            import gnubot

            ver = gnubot.__version__
        except Exception:
            ver = "0.0.0"
        return {
            "User-Agent": f"gnuChanBOT/{ver} (Discord bot; users.roblox.com; friends.roblox.com)",
            "Accept": "application/json",
        }

    def __init__(
        self,
        *,
        timeout_seconds: float = 25.0,
        max_retries: int = 4,
        cache_ttl_seconds: float = 45.0,
    ) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._user_cache: TTLCache[int, dict[str, Any]] = TTLCache(maxsize=2048, ttl=cache_ttl_seconds)
        self._follower_count_cache: TTLCache[int, int] = TTLCache(maxsize=2048, ttl=cache_ttl_seconds)
        self._username_cache: TTLCache[str, int] = TTLCache(maxsize=1024, ttl=cache_ttl_seconds)

    async def connect(self) -> None:
        """Open the underlying HTTP session."""

        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers=self._default_headers(),
            )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> RobloxClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _session_required(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("RobloxClient must be used as async context manager.")
        return self._session

    async def _get_json(self, url: str) -> dict[str, Any]:
        session = self._session_required()
        delay = 0.5
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with session.get(url) as resp:
                    text = await resp.text()
                    if resp.status == 429 or resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=text,
                        )
                    if resp.status >= 400:
                        raise RobloxAPIError(f"HTTP {resp.status} for {url}: {text[:500]}")
                    try:
                        return await resp.json()
                    except aiohttp.ContentTypeError as exc:
                        raise RobloxAPIError(f"Invalid JSON from {url}: {text[:200]}") from exc
            except (aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientResponseError) as exc:
                last_exc = exc
                logger.warning(
                    "Roblox GET attempt %s/%s failed: %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        raise RobloxAPIError(f"Failed after {self._max_retries} attempts: {last_exc}") from last_exc

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._session_required()
        delay = 0.5
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with session.post(url, json=payload) as resp:
                    text = await resp.text()
                    if resp.status == 429 or resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=text,
                        )
                    if resp.status >= 400:
                        raise RobloxAPIError(f"HTTP {resp.status} for {url}: {text[:500]}")
                    try:
                        return await resp.json()
                    except aiohttp.ContentTypeError as exc:
                        raise RobloxAPIError(f"Invalid JSON from {url}: {text[:200]}") from exc
            except (aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ClientResponseError) as exc:
                last_exc = exc
                logger.warning(
                    "Roblox POST attempt %s/%s failed: %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        raise RobloxAPIError(f"Failed after {self._max_retries} attempts: {last_exc}") from last_exc

    async def resolve_username_to_user_id(self, username: str) -> int:
        """
        Roblox display name / username → numeric user id (``POST /v1/usernames/users``).
        """

        key = username.strip()
        if not key:
            raise RobloxAPIError("Kullanıcı adı boş olamaz.")
        lookup = key[:60]
        canon = lookup.lower()
        cached = self._username_cache.get(canon)
        if cached is not None:
            return int(cached)

        url = f"{self.USERS_BASE}/v1/usernames/users"
        data = await self._post_json(
            url,
            {"usernames": [lookup], "excludeBannedUsers": True},
        )
        items = data.get("data") or []
        if not items:
            raise RobloxAPIError(f"Roblox kullanıcı adı bulunamadı: `{lookup}`")
        first = items[0]
        try:
            uid = int(first["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RobloxAPIError(f"Roblox yanıtı beklenmedik: {first!r}") from exc
        self._username_cache[canon] = uid
        return uid

    async def reconfigure(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        cache_ttl_seconds: float,
    ) -> None:
        """Apply new HTTP limits and clear in-memory caches (session recreated)."""

        self._max_retries = max(1, int(max_retries))
        self._timeout = aiohttp.ClientTimeout(total=float(timeout_seconds))
        ttl = float(cache_ttl_seconds)
        self._user_cache = TTLCache(maxsize=2048, ttl=ttl)
        self._follower_count_cache = TTLCache(maxsize=2048, ttl=ttl)
        self._username_cache = TTLCache(maxsize=1024, ttl=ttl)
        if self._session is not None:
            await self._session.close()
            self._session = None
        await self.connect()

    async def get_user(self, roblox_user_id: int) -> dict[str, Any]:
        cached = self._user_cache.get(roblox_user_id)
        if cached is not None:
            return cached
        url = f"{self.USERS_BASE}/v1/users/{roblox_user_id}"
        data = await self._get_json(url)
        self._user_cache[roblox_user_id] = data
        return data

    async def get_follower_count(self, roblox_user_id: int) -> int:
        cached = self._follower_count_cache.get(roblox_user_id)
        if cached is not None:
            return cached
        url = f"{self.FRIENDS_BASE}/v1/users/{roblox_user_id}/followers/count"
        data = await self._get_json(url)
        count = int(data.get("count", 0))
        self._follower_count_cache[roblox_user_id] = count
        return count

    async def iter_following_ids(self, roblox_user_id: int) -> set[int]:
        """
        Return the set of Roblox user IDs that ``roblox_user_id`` follows.

        Handles cursor pagination.
        """

        following: set[int] = set()
        cursor: str | None = None
        while True:
            q = "limit=200"
            if cursor:
                q += f"&cursor={cursor}"
            url = f"{self.FRIENDS_BASE}/v1/users/{roblox_user_id}/followings?{q}"
            data = await self._get_json(url)
            for item in data.get("data", []):
                try:
                    following.add(int(item["id"]))
                except (KeyError, TypeError, ValueError):
                    logger.warning("Unexpected followings payload item: %s", item)
            cursor = data.get("nextPageCursor")
            if not cursor:
                break
        return following
