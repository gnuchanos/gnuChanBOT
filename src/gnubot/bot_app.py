"""Discord bot wiring: intents, shared dependencies, background jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from gnubot.config.settings import Settings, get_settings
from gnubot.roblox import RobloxClient
from gnubot.scheduler.follow_checker import follow_checker_loop

from gnubot.services.cooldowns import CooldownTracker
from gnubot.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class GnuChanBot(commands.Bot):
    """
    Application bot with async SQLAlchemy session factory and Roblox client.

    Background follow verification runs on ``setup_hook``.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        roblox: RobloxClient,
        **kwargs: Any,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=settings.bot_command_prefix, intents=intents, **kwargs)
        self.settings = settings
        self.engine = engine
        self.session_factory = session_factory
        self.roblox = roblox
        self.rate_limiter = RateLimiter(
            settings.rate_limit_max_commands,
            float(settings.rate_limit_window_seconds),
        )
        self.cd_register = CooldownTracker()
        self.cd_tasks = CooldownTracker()
        self.cd_leaderboard = CooldownTracker()
        self.cd_check = CooldownTracker()
        self.cd_redemption = CooldownTracker()
        self.cd_taleplerim = CooldownTracker()
        self._follow_task: asyncio.Task[None] | None = None
        self.ready_at_utc: datetime | None = None

    async def reload_runtime_settings(self) -> str:
        """
        Re-read environment (``.env``) into ``self.settings`` and refresh in-memory helpers.

        ``RobloxClient`` HTTP zaman aşımı, yeniden deneme ve önbellek TTL burada güncellenir.
        Veritabanı motoru ve Discord oturumu yalnızca süreç yeniden başlatılarak değişir.
        """

        from pydantic import ValidationError

        get_settings.cache_clear()
        try:
            new_settings = get_settings()
        except ValidationError as exc:
            return (
                "`.env` doğrulanamadı; mevcut ayarlar korundu.\n"
                f"```{str(exc)[:1500]}```"
            )[:1900]

        self.settings = new_settings
        self.rate_limiter = RateLimiter(
            new_settings.rate_limit_max_commands,
            float(new_settings.rate_limit_window_seconds),
        )
        self.command_prefix = new_settings.bot_command_prefix
        try:
            await self.roblox.reconfigure(
                timeout_seconds=new_settings.roblox_http_timeout_seconds,
                max_retries=new_settings.roblox_max_retries,
                cache_ttl_seconds=new_settings.roblox_cache_ttl_seconds,
            )
        except Exception as exc:
            logger.exception("Roblox reconfigure after settings reload failed")
            return (
                "Ayarlar, hız limiti ve prefix güncellendi; **Roblox istemcisi** yenilenirken hata oluştu: "
                f"`{exc}` — loglara bak, gerekirse botu yeniden başlat."
            )[:1900]
        return (
            "Tamam: ayarlar, hız limiti, prefix ve **Roblox HTTP** (timeout / retry / önbellek) güncellendi. "
            "Takip döngüsü aralığı bir sonraki uyku adımından itibaren yeni değeri kullanır. "
            "`DATABASE_URL` veya `DISCORD_TOKEN` değiştiyse botu yeniden başlat."
        )

    async def setup_hook(self) -> None:
        await self.roblox.connect()
        await self.load_extension("gnubot.cogs.follow_cog")
        await self.load_extension("gnubot.cogs.admin_cog")
        try:
            await self.load_extension("gnubot.cogs.music_cog")
        except Exception:
            logger.warning("Music cog failed to load (optional).", exc_info=True)
        guild = discord.Object(id=self.settings.discord_guild_id) if self.settings.discord_guild_id else None
        if guild:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        async def on_tree_error(interaction: discord.Interaction, error: Exception) -> None:
            await self._handle_app_command_error(interaction, error)

        self.tree.error(on_tree_error)

        self._follow_task = asyncio.create_task(
            follow_checker_loop(self),
            name="follow-checker",
        )

    async def on_ready(self) -> None:
        user = self.user
        self.ready_at_utc = datetime.now(timezone.utc)
        logger.info("Bot ready: %s (%s)", user, user.id if user else None)
        await self.refresh_presence()

    async def refresh_presence(self) -> None:
        """Set ``watching`` activity from active client count (best-effort)."""

        try:
            from gnubot.infrastructure.database import open_session
            from gnubot.services.client_service import ClientService

            async with open_session(self.session_factory) as session:
                cs = ClientService(session)
                n = await cs.count_clients(active=True)
        except Exception:
            logger.exception("refresh_presence DB read failed")
            return
        label = f"{n} aktif görev" if n else "Aktif görev yok"
        if len(label) > 128:
            label = label[:125] + "…"
        try:
            await self.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name=label),
            )
        except Exception:
            logger.exception("change_presence failed")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Prefix komutlarında kullanıcıya kısa geri bildirim + log."""

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "Bu komut için kanalda **Mesajları Yönet** iznine ihtiyacın var.",
                delete_after=15,
            )
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send(
                "Botun bu kanalda komutu çalıştırmak için ek izinlere ihtiyacı olabilir (yöneticiye bildir).",
                delete_after=15,
            )
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Bu komutu şu an kullanamazsın.", delete_after=12)
            return
        orig: BaseException = error
        if isinstance(error, commands.CommandInvokeError) and error.original is not None:
            orig = error.original
        logger.exception(
            "Prefix komut hatası (command=%s user=%s)",
            ctx.command and ctx.command.name,
            ctx.author.id,
            exc_info=orig,
        )
        try:
            await ctx.send(
                "Komut çalışırken bir hata oluştu. Yöneticiye bildir veya loglara bak.",
                delete_after=20,
            )
        except Exception:
            logger.exception("Failed to send prefix error reply")

    async def close(self) -> None:
        if self._follow_task:
            self._follow_task.cancel()
            try:
                await self._follow_task
            except asyncio.CancelledError:
                pass
            self._follow_task = None
        await self.roblox.close()
        await self.engine.dispose()
        await super().close()

    async def _handle_app_command_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        """Slash komutlarında yakalanmamış hatalar için güvenli yanıt."""

        if isinstance(error, app_commands.CheckFailure):
            return
        exc: BaseException = error
        if isinstance(error, app_commands.CommandInvokeError) and error.original is not None:
            exc = error.original
        logger.exception(
            "Slash komut hatası (command=%s user=%s)",
            interaction.command and interaction.command.name,
            interaction.user and interaction.user.id,
            exc_info=exc,
        )
        msg = "Komut çalıştırılamadı. Kısa süre sonra tekrar dene veya yöneticiye bildir."
        if isinstance(exc, app_commands.TransformerError):
            msg = "Geçersiz parametre."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            logger.exception("Failed to send slash error message")
