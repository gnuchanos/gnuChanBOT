"""Slash commands for registration, tasks, leaderboard, and profile."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gnubot.services.client_service import ClientService
from gnubot.services.leaderboard_service import LeaderboardService
from gnubot.services.redemption_service import RedemptionService
from gnubot.services.user_service import UserService

if TYPE_CHECKING:
    from gnubot.bot_app import GnuChanBot

logger = logging.getLogger(__name__)


def _is_guild(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None


async def _interaction_checks(bot: GnuChanBot, interaction: discord.Interaction) -> bool:
    if not _is_guild(interaction):
        await interaction.response.send_message(
            "Bu komutlar yalnızca sunucuda kullanılabilir.",
            ephemeral=True,
        )
        return False
    if interaction.user and interaction.user.id in bot.settings.banned_id_set():
        await interaction.response.send_message(
            "Bu sunucuda bot komutlarını kullanman engellenmiş.",
            ephemeral=True,
        )
        return False
    if not bot.rate_limiter.allow(str(interaction.user.id)):
        await interaction.response.send_message(
            "Çok hızlı komut kullanıyorsun. Lütfen kısa süre sonra tekrar dene.",
            ephemeral=True,
        )
        return False
    return True


class FollowCog(commands.Cog):
    """User-facing slash commands."""

    def __init__(self, bot: GnuChanBot) -> None:
        self.bot = bot

    @app_commands.command(name="yardim", description="Komut özeti ve kullanım akışı")
    async def yardim(self, interaction: discord.Interaction) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        text = (
            "**Akış:** `/register` veya `/register_username` → `/tasks` → Roblox’ta hedefi takip et → "
            "`/check` (isteğe bağlı: `gorev_id`) → kredi.\n\n"
            "**Komutlar**\n"
            "• `/register` — Roblox **sayısal** ID (aynı Roblox iki Discord’a bağlanamaz)\n"
            "• `/register_username` — Roblox **kullanıcı adı** ile bağla\n"
            "• `/tasks` — Aktif görevler\n"
            "• `/check` — Takip doğrula, kredi al\n"
            "• `/profile` — Bakiye ve özet\n"
            "• `/leaderboard` — Sıralama (`senin_siran` ile yerin)\n"
            "• `/nakit_talep` — Nakit talebi (üst sınır ve bekleyen talep limiti `/profile`’da)\n"
            "• `/taleplerim` — Talep geçmişin\n"
            "• `/hakkinda` — Sürüm ve çalışma süresi\n"
            "• `/yardim` — Bu mesaj\n\n"
            "**Yönetici:** `/admin` grubu (`.env` içindeki `DISCORD_ADMIN_IDS`). "
            "Örnek: `roblox_collisions`, `client_get`, `redeem_get`, `user_lookup`, `user_unlink`, `redeem_list`, `stats`, `reload_config`, "
            "`client_refresh_followers`, `client_set_target`, `client_rename`."
        )
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="hakkinda", description="Bot sürümü ve çalışma bilgisi")
    async def hakkinda(self, interaction: discord.Interaction) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        import gnubot

        ver = gnubot.__version__
        since = getattr(self.bot, "ready_at_utc", None)
        if since:
            delta = datetime.now(timezone.utc) - since
            secs = int(delta.total_seconds())
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            uptime = f"{h}s {m}dk {s}sn" if h else (f"{m}dk {s}sn" if m else f"{s}sn")
        else:
            uptime = "—"
        lat_ms = round(self.bot.latency * 1000, 1) if self.bot.latency is not None else 0.0
        interval = int(self.bot.settings.follow_check_interval_seconds)
        embed = discord.Embed(title="gnuChanBOT", description=f"Sürüm **{ver}**")
        embed.add_field(name="Çalışma (bu oturum)", value=uptime, inline=True)
        embed.add_field(name="WS gecikmesi", value=f"~{lat_ms} ms", inline=True)
        embed.add_field(name="Sunucu sayısı", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Arka plan takip kontrolü",
            value=f"~{interval} sn (`FOLLOW_CHECK_INTERVAL_SECONDS`)",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="register", description="Roblox hesabını bağla")
    @app_commands.describe(roblox_id="Roblox kullanıcı ID (sayı)")
    async def register(self, interaction: discord.Interaction, roblox_id: int) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        if roblox_id <= 0:
            await interaction.response.send_message("Geçersiz Roblox ID.", ephemeral=True)
            return
        cd = self.bot.cd_register
        key = str(interaction.user.id)
        if not cd.ready(key, float(self.bot.settings.cooldown_register_seconds)):
            await interaction.response.send_message(
                f"Kayıt için {int(cd.remaining(key, float(self.bot.settings.cooldown_register_seconds)))} sn bekle.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.roblox.get_user(int(roblox_id))
        except Exception as exc:
            logger.exception("register roblox get_user failed")
            await interaction.followup.send(
                f"Roblox bu ID için kullanıcı bulunamadı veya şu an doğrulanamıyor: `{exc}`",
                ephemeral=True,
            )
            return

        cd.touch(key)

        from gnubot.infrastructure.database import open_session

        async with open_session(self.bot.session_factory) as session:
            svc = UserService(session)
            other = await svc.get_by_roblox_id(int(roblox_id))
            if other is not None and int(other.discord_id) != int(interaction.user.id):
                await interaction.followup.send(
                    "Bu Roblox hesabı **başka bir Discord kullanıcısına** zaten bağlı. "
                    "Yönetim çözdükten sonra tekrar dene.",
                    ephemeral=True,
                )
                return
            user = await svc.register_roblox(int(interaction.user.id), int(roblox_id))
            await session.refresh(user)
        await interaction.followup.send(
            f"Kayıt tamam. Roblox ID: **{user.roblox_id}** | Toplam kredi: **{user.points}**\n"
            f"Müşteri listesindeki hedefi Roblox’ta takip ettikten sonra **`/check`** ile doğrula; "
            f"kredi (ileride nakde çevrilebilir birim) yalnızca doğrulama sonrası eklenir.",
            ephemeral=True,
        )

    @app_commands.command(
        name="register_username",
        description="Roblox kullanıcı adı ile hesabını bağla (ID otomatik çözülür)",
    )
    @app_commands.describe(kullanici_adi="Roblox kullanıcı adı (ör. Builderman)")
    async def register_username(self, interaction: discord.Interaction, kullanici_adi: str) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        name = (kullanici_adi or "").strip()
        if len(name) < 3 or len(name) > 60:
            await interaction.response.send_message(
                "Kullanıcı adı **3–60** karakter arasında olmalı.",
                ephemeral=True,
            )
            return
        cd = self.bot.cd_register
        key = str(interaction.user.id)
        if not cd.ready(key, float(self.bot.settings.cooldown_register_seconds)):
            await interaction.response.send_message(
                f"Kayıt için {int(cd.remaining(key, float(self.bot.settings.cooldown_register_seconds)))} sn bekle.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        from gnubot.infrastructure.database import open_session
        from gnubot.roblox import RobloxAPIError

        try:
            rid = await self.bot.roblox.resolve_username_to_user_id(name)
            info = await self.bot.roblox.get_user(rid)
            display = str(info.get("name", rid))
        except RobloxAPIError as exc:
            await interaction.followup.send(f"Roblox: {exc}", ephemeral=True)
            return
        except Exception as exc:
            logger.exception("register_username roblox failed")
            await interaction.followup.send(f"Roblox hatası: `{exc}`", ephemeral=True)
            return

        cd.touch(key)
        async with open_session(self.bot.session_factory) as session:
            svc = UserService(session)
            other = await svc.get_by_roblox_id(int(rid))
            if other is not None and int(other.discord_id) != int(interaction.user.id):
                await interaction.followup.send(
                    "Bu Roblox hesabı **başka bir Discord kullanıcısına** zaten bağlı. "
                    "Yönetim çözdükten sonra tekrar dene.",
                    ephemeral=True,
                )
                return
            user = await svc.register_roblox(int(interaction.user.id), int(rid))
            await session.refresh(user)
        await interaction.followup.send(
            f"Kayıt tamam. Roblox: **{display}** (`{rid}`) | Toplam kredi: **{user.points}**\n"
            f"Hedefi takip ettikten sonra **`/check`** ile doğrula.",
            ephemeral=True,
        )

    @app_commands.command(
        name="check",
        description="Roblox’ta görev hedeflerini takip edip etmediğini doğrula ve kredi al",
    )
    @app_commands.describe(
        gorev_id="İsteğe bağlı: yalnızca bu görev numarası (#id) için doğrula",
    )
    async def check(self, interaction: discord.Interaction, gorev_id: int | None = None) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        cd = self.bot.cd_check
        key = str(interaction.user.id)
        cool = float(self.bot.settings.cooldown_check_seconds)
        if not cd.ready(key, cool):
            await interaction.response.send_message(
                f"Takip doğrulama için {cd.remaining(key, cool):.0f} sn bekle.",
                ephemeral=True,
            )
            return
        cd.touch(key)

        from gnubot.infrastructure.database import open_session
        from gnubot.services.follow_service import FollowService

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            async with open_session(self.bot.session_factory) as session:
                fs = FollowService(session)
                result = await fs.run_check_for_discord_user(
                    self.bot.roblox,
                    int(interaction.user.id),
                    reward_points=self.bot.settings.follow_reward_points,
                    penalty_points=self.bot.settings.follow_penalty_points,
                    client_id=int(gorev_id) if gorev_id is not None else None,
                )
        except Exception as exc:
            logger.exception("Roblox /check failed")
            await interaction.followup.send(
                f"Roblox doğrulaması şu an yapılamadı: `{exc}`\nBiraz sonra tekrar dene.",
                ephemeral=True,
            )
            return

        if result.error == "no_user":
            await interaction.followup.send(
                "Kayıt bulunamadı. `/register` veya `/register_username` kullan.",
                ephemeral=True,
            )
            return
        if result.error == "no_roblox":
            await interaction.followup.send(
                "Önce **`/register`** veya **`/register_username`** ile Roblox hesabını bağla.",
                ephemeral=True,
            )
            return
        if result.error == "client_not_found":
            await interaction.followup.send("Bu numaralı **görev yok** (`/tasks` ile id’leri kontrol et).", ephemeral=True)
            return
        if result.error == "client_inactive":
            await interaction.followup.send(
                "Bu görev **aktif değil** veya hedef tamamlanmış. `/tasks` ile güncel listeye bak.",
                ephemeral=True,
            )
            return
        if result.error == "no_active_tasks" or not result.rows:
            await interaction.followup.send(
                "Şu an **aktif görev** yok veya senkron için görev bulunamadı. `/tasks` ile listeyi kontrol et.",
                ephemeral=True,
            )
            return

        user = result.user
        rows = result.rows
        lines: list[str] = []
        for c, out in rows:
            label = c.display_name or f"Görev #{c.id}"
            tid = c.roblox_target_id
            if out.code == "rewarded":
                lines.append(
                    f"**#{c.id}** {label} (`{tid}`) — Takip **doğrulandı**; "
                    f"**+{out.points_delta}** kredi eklendi."
                )
            elif out.code == "penalized":
                lines.append(
                    f"**#{c.id}** {label} (`{tid}`) — Ödül sonrası takipten çıkış; "
                    f"**{out.points_delta}** kredi (ceza)."
                )
            elif out.code == "already_rewarded":
                lines.append(
                    f"**#{c.id}** {label} (`{tid}`) — Bu görev için kredi **zaten alınmış**; "
                    f"takip durumun güncel."
                )
            elif out.code == "not_following":
                lines.append(
                    f"**#{c.id}** {label} (`{tid}`) — Bu hesabı Roblox’ta **takip etmiyorsun** "
                    f"(veya liste gizli / API gecikmesi). Takip et, bir süre sonra tekrar `/check`."
                )
            elif out.code == "rewarded_unfollowed":
                lines.append(
                    f"**#{c.id}** {label} (`{tid}`) — Daha önce kredi almıştın; şu an **takipte değilsin**."
                )
            else:
                lines.append(f"**#{c.id}** {label} (`{tid}`) — Durum güncellendi (kredi değişmedi).")

        total = user.points if user else 0
        embed = discord.Embed(
            title="Takip doğrulama (/check)",
            description="\n".join(lines)[:4090],
        )
        embed.set_footer(text=f"Toplam kredi (puan): {total} — Nakde çevrim sunucu kurallarına bağlıdır.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="tasks", description="Aktif takip görevlerini listele")
    async def tasks(self, interaction: discord.Interaction) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        cd = self.bot.cd_tasks
        key = str(interaction.user.id)
        if not cd.ready(key, float(self.bot.settings.cooldown_tasks_seconds)):
            await interaction.response.send_message(
                f"Görev listesi için {cd.remaining(key, float(self.bot.settings.cooldown_tasks_seconds)):.0f} sn bekle.",
                ephemeral=True,
            )
            return
        cd.touch(key)

        from gnubot.infrastructure.database import open_session

        async with open_session(self.bot.session_factory) as session:
            cs = ClientService(session)
            rows = await cs.list_clients(active_only=True)
            inactive_n = await cs.count_clients(active=False)
            total_n = await cs.count_clients(active=None)
        if not rows:
            if total_n == 0:
                msg = "Henüz sistemde görev kaydı yok."
            elif inactive_n > 0:
                msg = (
                    f"Şu an **aktif görev yok**. Pasif görev: **{inactive_n}** "
                    "(hedef tamamlandı veya yönetici kapattı; yöneticiler `/admin client_list` ile tümünü görebilir)."
                )
            else:
                msg = "Şu an aktif görev yok."
            await interaction.response.send_message(msg, ephemeral=True)
            return
        lines: list[str] = []
        for c in rows:
            name = c.display_name or f"Hedef {c.roblox_target_id}"
            rid = int(c.roblox_target_id)
            profil = f"https://www.roblox.com/users/{rid}/profile"
            lines.append(
                f"**#{c.id}** — {name}\n"
                f"├ Roblox hedef: `{rid}` — [Profil]({profil})\n"
                f"└ İlerleme: `{c.current_followers}` / `{c.target_followers}` takipçi\n"
            )
        embed = discord.Embed(title="Aktif görevler", description="\n".join(lines))
        foot = (
            "Hedefi Roblox’ta takip et; ardından /check ile takip doğrulanınca kredi eklenir."
        )
        if inactive_n > 0:
            foot += f" | Pasif görev: {inactive_n}"
        embed.set_footer(text=foot)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="En yüksek krediler")
    @app_commands.describe(
        limit="Kaç kişi (1-25)",
        senin_siran="True ise mesaj altında sıralamadaki yerin gösterilir",
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        limit: int = 10,
        senin_siran: bool = False,
    ) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        limit = max(1, min(25, int(limit)))
        cd = self.bot.cd_leaderboard
        key = str(interaction.user.id)
        if not cd.ready(key, float(self.bot.settings.cooldown_leaderboard_seconds)):
            await interaction.response.send_message(
                f"Liderlik tablosu için {cd.remaining(key, float(self.bot.settings.cooldown_leaderboard_seconds)):.0f} sn bekle.",
                ephemeral=True,
            )
            return
        cd.touch(key)

        from gnubot.infrastructure.database import open_session

        async with open_session(self.bot.session_factory) as session:
            lb = LeaderboardService(session)
            users = await lb.top_by_points(limit=limit)
            rank: int | None = None
            my_pts = 0
            if senin_siran:
                rank, my_pts = await lb.rank_for_discord_user(int(interaction.user.id))
        if not users:
            await interaction.response.send_message("Henüz kredi kaydı yok.", ephemeral=True)
            return
        text_lines: list[str] = []
        for i, u in enumerate(users, start=1):
            text_lines.append(f"{i}. <@{u.discord_id}> — **{u.points}** kredi")
        embed = discord.Embed(title="Liderlik tablosu (kredi)", description="\n".join(text_lines))
        if senin_siran:
            if rank is not None:
                embed.set_footer(text=f"Senin sıran: #{rank} — bakiyen: {my_pts} kredi")
            else:
                embed.set_footer(text=f"Sıralamada değilsin (bakiye: {my_pts} kredi; listede olmak için kredi > 0).")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="nakit_talep",
        description="Kredi bakiyenden nakde çevirme / ödeme talebi oluştur (yönetici onayı)",
    )
    @app_commands.describe(
        miktar="Talep edilen kredi miktarı",
        not_mesaji="İsteğe bağlı kısa not (IBAN / ödeme yöntemi vb., 240 karakter)",
    )
    async def nakit_talep(
        self,
        interaction: discord.Interaction,
        miktar: int,
        not_mesaji: str | None = None,
    ) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        cd = self.bot.cd_redemption
        key = str(interaction.user.id)
        cool = float(self.bot.settings.cooldown_redemption_seconds)
        if not cd.ready(key, cool):
            await interaction.response.send_message(
                f"Talep için {cd.remaining(key, cool):.0f} sn bekle.",
                ephemeral=True,
            )
            return
        cd.touch(key)

        from gnubot.infrastructure.database import open_session

        max_single = int(self.bot.settings.max_single_redemption)
        max_pend = int(self.bot.settings.max_pending_redemptions_per_user)
        try:
            async with open_session(self.bot.session_factory) as session:
                rs = RedemptionService(session)
                req = await rs.create_request(
                    discord_id=int(interaction.user.id),
                    points=int(miktar),
                    note=not_mesaji,
                    max_pending_per_user=max_pend,
                    max_single_redemption=max_single,
                )
                rid = req.id
        except ValueError as ve:
            await interaction.response.send_message(str(ve), ephemeral=True)
            return

        lim_hint = (
            f"Limit: tek talepte en fazla **{max_single}** kredi"
            if max_single > 0
            else "Limit: tek talep üst sınırı yok (bakiyene kadar)"
        )
        await interaction.response.send_message(
            f"Talep **#{rid}** oluşturuldu (**{miktar}** kredi). Yönetici onayından sonra bakiyenden düşülür; "
            f"gerçek ödeme sunucu sürecine göre yapılır. Durum için `/profile` (bekleyen talep sayısı).\n"
            f"— {lim_hint}; aynı anda en fazla **{max_pend}** bekleyen talep.",
            ephemeral=True,
        )

    @app_commands.command(name="taleplerim", description="Nakit taleplerinin geçmişini listele")
    @app_commands.describe(limit="1-15 arası kayıt (varsayılan 10)")
    async def taleplerim(self, interaction: discord.Interaction, limit: int = 10) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        cd = self.bot.cd_taleplerim
        key = str(interaction.user.id)
        cool = float(self.bot.settings.cooldown_taleplerim_seconds)
        if not cd.ready(key, cool):
            await interaction.response.send_message(
                f"Liste için {cd.remaining(key, cool):.0f} sn bekle.",
                ephemeral=True,
            )
            return
        cd.touch(key)

        lim = max(1, min(15, int(limit)))
        from gnubot.infrastructure.database import open_session

        async with open_session(self.bot.session_factory) as session:
            rs = RedemptionService(session)
            rows = await rs.list_for_discord_user(int(interaction.user.id), limit=lim)
        if not rows:
            await interaction.response.send_message(
                "Henüz nakit talebin yok. `/nakit_talep` ile oluşturabilirsin.",
                ephemeral=True,
            )
            return
        lines: list[str] = []
        for r in rows:
            note = (r.note or "—").strip() or "—"
            if len(note) > 80:
                note = note[:77] + "…"
            if r.resolved_at:
                ts = r.resolved_at.strftime("%Y-%m-%d %H:%M UTC")
                durum_satir = f"çözümlendi ({ts})"
            else:
                durum_satir = "bekliyor"
            lines.append(
                f"**#{r.id}** `{r.status}` — **{r.points}** kredi — {durum_satir}\n"
                f"└ Not: {note}"
            )
        embed = discord.Embed(
            title="Nakit taleplerin",
            description="\n".join(lines)[:4000],
        )
        embed.set_footer(text="Onay/ret yöneticiler tarafından işlenir; bakiye yalnızca onayda düşer.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="profile", description="Profilini göster")
    async def profile(self, interaction: discord.Interaction) -> None:
        if not await _interaction_checks(self.bot, interaction):
            return
        from gnubot.infrastructure.database import open_session

        async with open_session(self.bot.session_factory) as session:
            svc = UserService(session)
            user = await svc.get_by_discord_id(int(interaction.user.id))
            pending = 0
            if user is not None:
                rs = RedemptionService(session)
                pending = await rs.pending_count_for_discord(int(interaction.user.id))
        if user is None:
            await interaction.response.send_message(
                "Henüz kayıtlı değilsin. `/register` veya `/register_username` ile Roblox hesabını bağla.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Profilin",
            description="Roblox bağlantısı ve **kredi (puan)** özeti. Kredi, `/check` ile takip doğrulandıkça eklenir.",
        )
        rid = user.roblox_id
        if rid is not None:
            url = f"https://www.roblox.com/users/{int(rid)}/profile"
            rbx_val = f"`{rid}` — [Roblox profili]({url})"
        else:
            rbx_val = "— (henüz bağlı değil)"
        embed.add_field(name="Roblox", value=rbx_val, inline=False)
        embed.add_field(name="Toplam kredi (puan)", value=str(user.points), inline=True)
        embed.add_field(name="Aktif takip", value=str(user.active_follows), inline=True)
        embed.add_field(name="Kredi alınmış görevler", value=str(user.completed_follows), inline=True)
        embed.add_field(name="Bekleyen nakit talebi", value=str(pending), inline=True)
        mx = int(self.bot.settings.max_single_redemption)
        mp = int(self.bot.settings.max_pending_redemptions_per_user)
        if mx > 0:
            lim_txt = f"Tek talepte en fazla **{mx}** kredi; aynı anda en fazla **{mp}** bekleyen talep."
        else:
            lim_txt = f"Tek talep üst sınırı yok; aynı anda en fazla **{mp}** bekleyen talep."
        embed.add_field(name="Nakit talep limitleri", value=lim_txt, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FollowCog(bot))  # type: ignore[arg-type]
