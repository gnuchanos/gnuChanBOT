"""Administrative slash commands and legacy prefix moderation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gnubot.infrastructure.database import open_session
from gnubot.utils.prefix_access import prefix_ban_message
from gnubot.services.client_service import ClientService
from gnubot.services.follow_service import FollowService
from gnubot.services.redemption_service import RedemptionService
from gnubot.services.stats_service import StatsService
from gnubot.services.user_service import UserService

if TYPE_CHECKING:
    from gnubot.bot_app import GnuChanBot

logger = logging.getLogger(__name__)


async def _admin_app_check(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    if not isinstance(bot, commands.Bot):
        return False
    # Avoid circular typing; runtime uses settings on concrete bot class.
    settings = getattr(bot, "settings", None)
    admin_ids = settings.admin_id_set() if settings is not None else set()
    if not admin_ids:
        await interaction.response.send_message(
            "`DISCORD_ADMIN_IDS` yapılandırılmamış. Tüm admin komutları kapalı.",
            ephemeral=True,
        )
        return False
    if interaction.user.id not in admin_ids:
        await interaction.response.send_message("Bu komut için yetkin yok.", ephemeral=True)
        return False
    return True


_admin_only = app_commands.check(_admin_app_check)


def schedule_presence_refresh(bot: commands.Bot) -> None:
    """Fire-and-forget Discord presence refresh when active task counts may have changed."""

    fn = getattr(bot, "refresh_presence", None)
    if fn is None or not callable(fn):
        return
    try:
        asyncio.get_running_loop().create_task(fn())
    except RuntimeError:
        pass


class AdminCog(commands.Cog):
    """Privileged operations (numeric Discord IDs in ``DISCORD_ADMIN_IDS``)."""

    admin = app_commands.Group(name="admin", description="Yönetim komutları")

    def __init__(self, bot: "GnuChanBot") -> None:
        self.bot = bot

    @admin.command(name="client_add", description="Yeni müşteri / görev ekle")
    @_admin_only
    @app_commands.describe(
        roblox_target_id="Hedef Roblox kullanıcı ID",
        target_followers="Hedef toplam takipçi sayısı",
        display_name="Opsiyonel kısa isim",
    )
    async def admin_client_add(
        self,
        interaction: discord.Interaction,
        roblox_target_id: int,
        target_followers: int,
        display_name: str | None = None,
    ) -> None:
        if roblox_target_id <= 0 or target_followers <= 0:
            await interaction.response.send_message("Geçersiz parametre.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            info = await self.bot.roblox.get_user(int(roblox_target_id))
        except Exception as exc:
            logger.exception("Roblox lookup failed")
            await interaction.followup.send(f"Roblox doğrulaması başarısız: `{exc}`", ephemeral=True)
            return
        name = display_name or str(info.get("name", roblox_target_id))
        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            try:
                count = await self.bot.roblox.get_follower_count(int(roblox_target_id))
            except Exception:
                count = 0
            c = await cs.add_client(
                int(roblox_target_id),
                int(target_followers),
                current_followers=count,
                display_name=name,
            )
            await session.refresh(c)
        await interaction.followup.send(
            f"Görev eklendi **#{c.id}** — `{name}`\n"
            f"Hedef: `{c.current_followers}` / `{c.target_followers}` (Roblox anlık)",
            ephemeral=True,
        )
        logger.info(
            "admin client_add actor=%s client_id=%s roblox_target=%s target_followers=%s",
            interaction.user.id,
            c.id,
            roblox_target_id,
            target_followers,
        )
        schedule_presence_refresh(self.bot)

    @admin.command(name="client_list", description="Tüm görevleri listele")
    @_admin_only
    @app_commands.describe(active_only="Yalnızca aktifleri göster")
    async def admin_client_list(self, interaction: discord.Interaction, active_only: bool = False) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            rows = await cs.list_clients(active_only=active_only)
        if not rows:
            await interaction.followup.send("Kayıt yok.", ephemeral=True)
            return
        lines: list[str] = []
        for c in rows[:40]:
            st = "aktif" if c.active else "pasif"
            lines.append(
                f"**#{c.id}** [{st}] hedef `{c.roblox_target_id}` "
                f"— `{c.current_followers}/{c.target_followers}`"
            )
        text = "\n".join(lines)
        if len(rows) > 40:
            text += f"\n… ve {len(rows) - 40} kayıt daha"
        await interaction.followup.send(text, ephemeral=True)

    @admin.command(name="client_get", description="Tek görev kaydının ayrıntısını göster")
    @_admin_only
    @app_commands.describe(client_id="clients.id")
    async def admin_client_get(
        self,
        interaction: discord.Interaction,
        client_id: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            c = await cs.get(int(client_id))
        if c is None:
            await interaction.followup.send("Görev bulunamadı.", ephemeral=True)
            return
        rid = int(c.roblox_target_id)
        prof = f"https://www.roblox.com/users/{rid}/profile"
        label = c.display_name or "—"
        st = "aktif" if c.active else "pasif"
        created = c.created_at.strftime("%Y-%m-%d %H:%M UTC") if c.created_at else "—"
        text = (
            f"**Görev #{c.id}** [{st}]\n"
            f"**Görünen ad:** {label}\n"
            f"**Roblox hedef:** `{rid}` — [Profil]({prof})\n"
            f"**Takipçi:** `{c.current_followers}` / `{c.target_followers}`\n"
            f"**Oluşturulma (UTC):** {created}"
        )
        await interaction.followup.send(text, ephemeral=True)

    @admin.command(name="client_set_active", description="Görevi aktif/pasif yap")
    @_admin_only
    async def admin_client_set_active(
        self,
        interaction: discord.Interaction,
        client_id: int,
        active: bool,
    ) -> None:
        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            c = await cs.set_active(client_id, active)
        if c is None:
            await interaction.response.send_message("Görev bulunamadı.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Görev **#{c.id}** artık **{'aktif' if c.active else 'pasif'}**.",
            ephemeral=True,
        )
        schedule_presence_refresh(self.bot)

    @admin.command(name="client_set_target", description="Görevin hedef takipçi sayısını güncelle")
    @_admin_only
    @app_commands.describe(
        client_id="clients.id (görev numarası)",
        target_followers="Yeni hedef toplam takipçi",
    )
    async def admin_client_set_target(
        self,
        interaction: discord.Interaction,
        client_id: int,
        target_followers: int,
    ) -> None:
        if target_followers <= 0:
            await interaction.response.send_message("Hedef pozitif bir sayı olmalı.", ephemeral=True)
            return
        try:
            async with open_session(self.bot.session_factory) as session:
                cs = ClientService(session)
                c = await cs.set_target_followers(int(client_id), int(target_followers))
        except ValueError as ve:
            await interaction.response.send_message(str(ve), ephemeral=True)
            return
        if c is None:
            await interaction.response.send_message("Görev bulunamadı.", ephemeral=True)
            return
        logger.info(
            "admin client_set_target actor=%s client_id=%s target=%s active=%s",
            interaction.user.id,
            c.id,
            c.target_followers,
            c.active,
        )
        await interaction.response.send_message(
            f"Görev **#{c.id}** hedefi **{c.target_followers}** olarak güncellendi. "
            f"Anlık Roblox: `{c.current_followers}` — durum: **{'aktif' if c.active else 'pasif'}**.",
            ephemeral=True,
        )
        schedule_presence_refresh(self.bot)

    @admin.command(name="client_rename", description="Görevin kısa görünen adını değiştir veya temizle")
    @_admin_only
    @app_commands.describe(
        client_id="clients.id",
        display_name="Yeni kısa isim; tamamen boş bırakılırsa isim silinir (Roblox ID gösterilir)",
    )
    async def admin_client_rename(
        self,
        interaction: discord.Interaction,
        client_id: int,
        display_name: str | None = None,
    ) -> None:
        raw = (display_name or "").strip()
        name: str | None = raw if raw else None
        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            c = await cs.set_display_name(int(client_id), name)
        if c is None:
            await interaction.response.send_message("Görev bulunamadı.", ephemeral=True)
            return
        logger.info(
            "admin client_rename actor=%s client_id=%s name=%r",
            interaction.user.id,
            c.id,
            c.display_name,
        )
        shown = c.display_name or f"(yok — hedef `{c.roblox_target_id}`)"
        await interaction.response.send_message(
            f"Görev **#{c.id}** görünen adı: **{shown}**",
            ephemeral=True,
        )

    @admin.command(
        name="client_refresh_followers",
        description="Tek görev için Roblox takipçi sayısını çek ve aktif/pasif durumunu güncelle",
    )
    @_admin_only
    @app_commands.describe(client_id="clients.id")
    async def admin_client_refresh_followers(
        self,
        interaction: discord.Interaction,
        client_id: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with open_session(self.bot.session_factory) as session:
                cs = ClientService(session)
                c = await cs.refresh_single_follower_count(self.bot.roblox, int(client_id))
        except Exception as exc:
            logger.exception("client_refresh_followers failed")
            await interaction.followup.send(f"Roblox veya veritabanı hatası: `{exc}`", ephemeral=True)
            return
        if c is None:
            await interaction.followup.send("Görev bulunamadı.", ephemeral=True)
            return
        logger.info(
            "admin client_refresh_followers actor=%s client_id=%s current=%s target=%s active=%s",
            interaction.user.id,
            c.id,
            c.current_followers,
            c.target_followers,
            c.active,
        )
        await interaction.followup.send(
            f"Görev **#{c.id}** güncellendi: Roblox takipçi **`{c.current_followers}`** / hedef **`{c.target_followers}`** "
            f"— **{'aktif' if c.active else 'pasif'}**.",
            ephemeral=True,
        )
        schedule_presence_refresh(self.bot)

    @admin.command(name="sync_now", description="Roblox senkronunu hemen çalıştır")
    @_admin_only
    async def admin_sync_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with open_session(self.bot.session_factory) as session:
                cs = ClientService(session)
                await cs.refresh_follower_counts(self.bot.roblox)
                fs = FollowService(session)
                n = await fs.sync_all_users(
                    self.bot.roblox,
                    reward_points=self.bot.settings.follow_reward_points,
                    penalty_points=self.bot.settings.follow_penalty_points,
                )
        except Exception as exc:
            logger.exception("Manual sync failed")
            await interaction.followup.send(f"Senkron hatası: `{exc}`", ephemeral=True)
            return
        await interaction.followup.send(
            f"Senkron tamam. İşlenen kullanıcı: **{n}** "
            f"(takip durumu + cezalar; **yeni +kredi** yalnızca kullanıcıların `/check` ile alınır).",
            ephemeral=True,
        )
        logger.info("admin sync_now actor=%s users_synced=%s", interaction.user.id, n)
        schedule_presence_refresh(self.bot)

    @admin.command(name="user_setpoints", description="Kullanıcı puanını ayarla")
    @_admin_only
    async def admin_user_setpoints(
        self,
        interaction: discord.Interaction,
        discord_user: discord.User,
        points: int,
    ) -> None:
        async with open_session(self.bot.session_factory) as session:
            us = UserService(session)
            user = await us.ensure_user(int(discord_user.id))
            user.points = int(points)
        logger.info(
            "admin user_setpoints actor=%s target=%s points=%s",
            interaction.user.id,
            discord_user.id,
            points,
        )
        await interaction.response.send_message(
            f"{discord_user.mention} kredi bakiyesi **{points}** olarak ayarlandı.",
            ephemeral=True,
        )

    @admin.command(name="user_lookup", description="Kullanıcı özeti (Roblox, kredi, talepler)")
    @_admin_only
    async def admin_user_lookup(
        self,
        interaction: discord.Interaction,
        discord_user: discord.User,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with open_session(self.bot.session_factory) as session:
            us = UserService(session)
            rs = RedemptionService(session)
            db_user = await us.get_by_discord_id(int(discord_user.id))
            if db_user is None:
                await interaction.followup.send(
                    f"{discord_user.mention} veritabanında yok (henüz hiç komut kullanmamış).",
                    ephemeral=True,
                )
                return
            pending = await rs.count_pending_for_user(db_user.id)
            rbx = db_user.roblox_id
            points = db_user.points
            active_follows = db_user.active_follows
            completed_follows = db_user.completed_follows
            recent = await rs.list_for_discord_user(int(discord_user.id), limit=3)
        prof = f"https://www.roblox.com/users/{rbx}/profile" if rbx else "— (bağlı değil)"
        recent_bits = [
            f"#{r.id} `{r.status}` **{r.points}**"
            for r in recent
        ]
        recent_line = " | ".join(recent_bits) if recent_bits else "—"
        text = (
            f"{discord_user.mention} (`{discord_user.id}`)\n"
            f"**Roblox ID:** `{rbx or '—'}`\n"
            f"**Profil:** {prof}\n"
            f"**Kredi:** **{points}**\n"
            f"**Aktif takip sayısı (özet):** `{active_follows}` | **Ödüllü:** `{completed_follows}`\n"
            f"**Bekleyen nakit talebi:** `{pending}`\n"
            f"**Son nakit talepleri (en fazla 3):** {recent_line}"
        )
        await interaction.followup.send(text[:3900], ephemeral=True)

    @admin.command(
        name="user_unlink",
        description="Roblox bağlantısını kaldır ve takip geçmişini sıfırla (kredi korunur)",
    )
    @_admin_only
    async def admin_user_unlink(
        self,
        interaction: discord.Interaction,
        discord_user: discord.User,
    ) -> None:
        async with open_session(self.bot.session_factory) as session:
            us = UserService(session)
            u = await us.clear_roblox_link(int(discord_user.id))
        if u is None:
            await interaction.response.send_message(
                f"{discord_user.mention} veritabanında yok.",
                ephemeral=True,
            )
            return
        logger.info(
            "admin user_unlink actor=%s target=%s points=%s",
            interaction.user.id,
            discord_user.id,
            u.points,
        )
        await interaction.response.send_message(
            f"{discord_user.mention} Roblox bağlantısı kaldırıldı; takip geçmişi silindi. "
            f"Mevcut kredi: **{u.points}**.",
            ephemeral=True,
        )

    @admin.command(
        name="roblox_collisions",
        description="Aynı Roblox kullanıcı ID’sine bağlı birden fazla Discord hesabını listele",
    )
    @_admin_only
    @app_commands.describe(
        max_grup="En fazla kaç çakışan Roblox ID gösterilsin (1-40, varsayılan 20)",
    )
    async def admin_roblox_collisions(
        self,
        interaction: discord.Interaction,
        max_grup: int = 20,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        lim = max(1, min(40, int(max_grup)))
        async with open_session(self.bot.session_factory) as session:
            details = await StatsService(session).roblox_collision_details(max_groups=lim)
        if not details:
            await interaction.followup.send(
                "Roblox ID çakışması yok (aynı Roblox’a birden fazla Discord bağlı kayıt bulunmuyor).",
                ephemeral=True,
            )
            return
        lines: list[str] = []
        for rid, dids in details:
            mentions = ", ".join(f"<@{d}>" for d in dids)
            lines.append(f"**Roblox `{rid}`:** {mentions}")
        logger.info(
            "admin roblox_collisions actor=%s groups_shown=%s",
            interaction.user.id,
            len(details),
        )
        await interaction.followup.send(
            "**Çakışmalar** (kısmi benzersiz indeks için veriyi düzelt; `/admin user_unlink`):\n"
            + "\n".join(lines)[:3850],
            ephemeral=True,
        )

    @admin.command(name="redeem_list", description="Nakit / ödeme taleplerini listele")
    @_admin_only
    @app_commands.describe(
        durum="pending | approved | rejected — boş bırakılırsa son talepler (hepsi)",
        limit="En fazla kaç kayıt (1-40)",
    )
    async def admin_redeem_list(
        self,
        interaction: discord.Interaction,
        durum: str | None = None,
        limit: int = 20,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        st = (durum or "").strip().lower() or None
        if st and st not in ("pending", "approved", "rejected"):
            await interaction.followup.send(
                "`durum` şunlardan biri olmalı: pending, approved, rejected veya boş.",
                ephemeral=True,
            )
            return
        lim = max(1, min(40, int(limit)))
        async with open_session(self.bot.session_factory) as session:
            rs = RedemptionService(session)
            rows = await rs.list_by_status(st, limit=lim)
        if not rows:
            await interaction.followup.send("Kayıt yok.", ephemeral=True)
            return
        lines: list[str] = []
        for req, u in rows:
            created = req.created_at.strftime("%Y-%m-%d %H:%M UTC") if req.created_at else "—"
            tail = f"oluşturma: {created}"
            if req.resolved_at:
                res = req.resolved_at.strftime("%Y-%m-%d %H:%M UTC")
                who = f"<@{req.resolver_discord_id}>" if req.resolver_discord_id else "—"
                tail += f" · çözüm: {res} · işlem: {who}"
            lines.append(
                f"**#{req.id}** [{req.status}] <@{u.discord_id}> — **{req.points}** kredi ({tail})"
            )
        await interaction.followup.send("\n".join(lines)[:3900], ephemeral=True)

    @admin.command(name="redeem_get", description="Tek nakit talebinin ayrıntısı")
    @_admin_only
    @app_commands.describe(talep_id="redemption_requests.id")
    async def admin_redeem_get(
        self,
        interaction: discord.Interaction,
        talep_id: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with open_session(self.bot.session_factory) as session:
            rs = RedemptionService(session)
            pair = await rs.get_with_user(int(talep_id))
            if pair is None:
                await interaction.followup.send("Talep bulunamadı.", ephemeral=True)
                return
            req, u = pair
            balance = int(u.points)
            discord_id = int(u.discord_id)
        note = (req.note or "—").strip() or "—"
        admin_note = (req.admin_note or "—").strip() or "—"
        res_at = req.resolved_at.strftime("%Y-%m-%d %H:%M UTC") if req.resolved_at else "—"
        res_by = f"<@{req.resolver_discord_id}>" if req.resolver_discord_id else "—"
        created = req.created_at.strftime("%Y-%m-%d %H:%M UTC") if req.created_at else "—"
        text = (
            f"**Talep #{req.id}** — `{req.status}`\n"
            f"**Kullanıcı:** <@{discord_id}> (şu anki bakiye **{balance}** kredi)\n"
            f"**Talep miktarı:** **{req.points}** kredi\n"
            f"**Oluşturma (UTC):** {created}\n"
            f"**Kullanıcı notu:** {note[:500]}\n"
            f"**Çözüm (UTC):** {res_at} — **işlem yapan:** {res_by}\n"
            f"**Yönetici notu:** {admin_note[:500]}"
        )
        await interaction.followup.send(text[:3900], ephemeral=True)

    @admin.command(name="redeem_resolve", description="Nakit talebini onayla veya reddet")
    @_admin_only
    @app_commands.describe(
        talep_id="redemption_requests.id",
        onayla="True = bakiyeden düş ve onayla, False = reddet",
        admin_notu="İsteğe bağlı not (kullanıcıya / kayıt için)",
    )
    async def admin_redeem_resolve(
        self,
        interaction: discord.Interaction,
        talep_id: int,
        onayla: bool,
        admin_notu: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with open_session(self.bot.session_factory) as session:
                rs = RedemptionService(session)
                _req, msg = await rs.resolve(
                    request_id=int(talep_id),
                    approve=bool(onayla),
                    resolver_discord_id=int(interaction.user.id),
                    admin_note=admin_notu,
                )
        except ValueError as ve:
            await interaction.followup.send(str(ve), ephemeral=True)
            return
        except Exception as exc:
            logger.exception("redeem_resolve failed")
            await interaction.followup.send(f"Hata: `{exc}`", ephemeral=True)
            return
        logger.info(
            "admin redeem_resolve actor=%s talep_id=%s onayla=%s msg=%s",
            interaction.user.id,
            talep_id,
            onayla,
            msg[:200],
        )
        await interaction.followup.send(msg, ephemeral=True)

    @admin.command(name="stats", description="Veritabanı özeti ve Roblox API gecikmesi")
    @_admin_only
    async def admin_stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        import time

        t0 = time.perf_counter()
        rbx_txt = "—"
        try:
            await self.bot.roblox.get_user(1)
            ms = (time.perf_counter() - t0) * 1000
            rbx_txt = f"~{round(ms, 0)} ms (`GET /users/1`)"
        except Exception as exc:
            rbx_txt = f"Hata: `{exc}`"

        async with open_session(self.bot.session_factory) as session:
            d = await StatsService(session).dashboard()

        lat = round(self.bot.latency * 1000, 1) if self.bot.latency else 0.0
        ready = getattr(self.bot, "ready_at_utc", None)
        since = ready.strftime("%Y-%m-%d %H:%M UTC") if ready else "—"
        clients_inactive = max(0, d.clients_total - d.clients_active)

        text = (
            f"**Kullanıcılar:** {d.users_total} toplam, **{d.users_with_roblox}** Roblox bağlı\n"
            f"**Toplam kredi (tüm kullanıcılar):** **{d.total_user_points}**\n"
            f"**Görevler:** {d.clients_total} kayıt, **{d.clients_active}** aktif, **{clients_inactive}** pasif\n"
            f"**Takip kayıtları (follow_history):** {d.follow_history_rows} satır, "
            f"**{d.follow_history_rewarded_rows}** ödüllendirilmiş (en az bir kez `/check` ile kredi)\n"
            f"**Roblox ID çakışması:** {d.roblox_collision_groups} grup "
            f"(detay: `/admin roblox_collisions`)\n"
            f"**Bekleyen nakit:** {d.redemptions_pending} talep, toplam **{d.pending_redemption_points}** kredi (onay bekliyor)\n"
            f"**Onaylanmış nakit talepleri:** {d.redemptions_approved_count} kayıt, toplam **{d.approved_redemption_points_total}** kredi\n"
            f"**Reddedilmiş nakit talepleri:** {d.redemptions_rejected_count} kayıt, talep edilen toplam **{d.rejected_redemption_points_total}** kredi\n"
            f"**Discord WS:** ~{lat} ms\n"
            f"**Roblox:** {rbx_txt}\n"
            f"**Bot ready (UTC):** {since}"
        )
        await interaction.followup.send(text, ephemeral=True)

    @admin.command(
        name="reload_config",
        description=".env / ortam değişkenlerini yeniden oku (yeniden başlatmadan kısmi güncelleme)",
    )
    @_admin_only
    async def admin_reload_config(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        msg = await self.bot.reload_runtime_settings()
        logger.info("admin reload_config actor=%s", interaction.user.id)
        await interaction.followup.send(msg, ephemeral=True)

    @commands.command(name="temizle")
    @commands.has_permissions(manage_messages=True)
    async def purge_prefix(self, ctx: commands.Context, arg: str | None = None) -> None:
        """Legacy prefix purge."""

        ban = prefix_ban_message(self.bot, int(ctx.author.id))
        if ban:
            await ctx.send(ban)
            return
        if not arg:
            await ctx.send("Kullanım: `$temizle hepsi` veya `$temizle <sayı>`")
            return
        if arg.lower() == "hepsi":
            while True:
                deleted = await ctx.channel.purge(limit=100)  # type: ignore[arg-type]
                if len(deleted) < 100:
                    break
            await ctx.send("Tüm mesajlar silindi.", delete_after=3)
            return
        if not arg.isdigit():
            await ctx.send("Kullanım: `$temizle hepsi` veya `$temizle <sayı>`")
            return
        n = int(arg)
        await ctx.channel.purge(limit=n + 1)  # type: ignore[arg-type]
        await ctx.send(f"{n} mesaj silindi.", delete_after=3)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))  # type: ignore[arg-type]
