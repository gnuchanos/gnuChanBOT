"""Legacy music commands (prefix ``hey``)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from gnubot.utils.prefix_access import prefix_ban_message

if TYPE_CHECKING:
    from gnubot.bot_app import GnuChanBot

logger = logging.getLogger(__name__)

try:
    import yt_dlp
except ImportError:  # pragma: no cover
    yt_dlp = None


class MusicCog(commands.Cog):
    def __init__(self, bot: GnuChanBot) -> None:
        self.bot = bot
        self.music_queue: list[tuple[str, str]] = []

    def _ffmpeg_executable(self) -> str | None:
        return getattr(self.bot.settings, "ffmpeg_path", None)

    def play_next(self, ctx: commands.Context) -> None:
        if not self.music_queue:
            return
        if ctx.voice_client is None:
            return
        audio_url, _title = self.music_queue.pop(0)
        opts: dict = {}
        exe = self._ffmpeg_executable()
        if exe:
            opts["executable"] = exe
        try:
            source = discord.FFmpegPCMAudio(audio_url, **opts)
        except Exception:
            logger.exception("FFmpeg failed to open audio")
            asyncio.create_task(ctx.send("FFmpeg hatası. `FFMPEG_PATH` ayarını kontrol et."))
            return
        ctx.voice_client.play(source, after=lambda _e: self.play_next(ctx))

    @commands.command(name="hey")
    async def hey(self, ctx: commands.Context, *args: str) -> None:
        ban = prefix_ban_message(self.bot, int(ctx.author.id))
        if ban:
            await ctx.send(ban)
            return
        if yt_dlp is None:
            await ctx.send("yt-dlp yüklü değil; müzik komutları devre dışı.")
            return
        if not args:
            await ctx.send("Komut belirtmedin.")
            return
        cmd = args[0].lower()
        if cmd == "gel":
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send("Ses kanalında değilsin.")
                return
            if ctx.voice_client:
                await ctx.send("Zaten seslideyim.")
                return
            await ctx.author.voice.channel.connect()
            await ctx.send("Ses kanalına bağlandım.")
            return
        if cmd == "git":
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
                await ctx.send("Çıktım.")
            else:
                await ctx.send("Zaten seslide değilim.")
            return
        if cmd == "oynat":
            if len(args) < 2:
                await ctx.send("Kullanım: `$hey oynat <youtube url>`")
                return
            if not ctx.voice_client:
                if ctx.author.voice and ctx.author.voice.channel:
                    await ctx.author.voice.channel.connect()
                else:
                    await ctx.send("Önce ses kanalına gir.")
                    return
            url = args[1]
            ydl_opts = {"format": "bestaudio/best", "quiet": True, "ignoreerrors": True}
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception:
                logger.exception("yt-dlp extract failed")
                await ctx.send("Video alınamadı.")
                return
            if info is None:
                await ctx.send("Video alınamadı.")
                return
            if "entries" in info:
                added = 0
                for entry in info["entries"] or []:
                    if not entry:
                        continue
                    self.music_queue.append((entry["url"], entry.get("title", "unknown")))
                    added += 1
                await ctx.send(f"Playlistten {added} parça kuyruğa eklendi.")
            else:
                self.music_queue.append((info["url"], info.get("title", "unknown")))
                await ctx.send(f"Kuyruğa eklendi: **{info.get('title', 'unknown')}**")
            if ctx.voice_client and not ctx.voice_client.is_playing():
                self.play_next(ctx)
            return
        if cmd == "gec":
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
                await ctx.send("Geçildi.")
            else:
                await ctx.send("Çalan yok.")
            return
        if cmd == "durdur":
            self.music_queue.clear()
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.send("Durduruldu, kuyruk temizlendi.")
            return
        if cmd == "liste":
            if not self.music_queue:
                await ctx.send("Kuyruk boş.")
                return
            lines = [f"{i+1}. {t}" for i, (_u, t) in enumerate(self.music_queue)]
            await ctx.send("Oynatma listesi:\n" + "\n".join(lines))
            return
        await ctx.send("Bilinmeyen komut.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))  # type: ignore[arg-type]
