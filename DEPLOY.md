# gnuChanBOT — Deploy Guide

## Prerequisites

- Python 3.11+ (3.12 recommended)
- A Discord application bot token with **Message Content Intent** enabled if you use prefix commands; for slash commands, enable the **applications.commands** scope when inviting the bot.
- Optional: `ffmpeg` on the host for the legacy music commands.

## Local setup

1. Create a virtual environment and install dependencies:

```bash
cd G:\gnuChanBOT
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`, `DISCORD_ADMIN_IDS`, and `DATABASE_URL`.

3. Run from the `src` directory so imports resolve:

```bash
cd src
python gnuchanos_bot.py
```

On first run the database schema is created automatically (`create_all`).

## Docker

```bash
docker compose build
docker compose up -d
```

Mount `/data` (already in `docker-compose.yml`) so SQLite survives restarts. For PostgreSQL, use `DATABASE_URL=postgresql+asyncpg://...` and run a Postgres container or managed database.

## Inviting the bot

Generate an invite URL with scopes `bot` and `applications.commands`, and permissions your server needs (e.g. Send Messages, Embed Links, Use Slash Commands, Manage Messages for purge if used).

## Komutlar — detaylı referans

**Tipik akış:** `/register` veya `/register_username` → `/tasks` → Roblox’ta hedefi takip et → **`/check`** → kredi. **`/nakit_talep`** / **`/taleplerim`** ile ödeme talebi ve geçmiş. Yönetici onayından sonra bakiyeden düşülür (gerçek ödeme bot dışında).

Önek: slash komutları `/` ile yazılır; prefix komutları `.env` içindeki `BOT_COMMAND_PREFIX` ile başlar (varsayılan **`$`**).

### Slash komutları — kim kullanır, nerede çalışır

| Komut | Kim | Kanal | Görünürlük / not |
|--------|-----|--------|-------------------|
| `/register` | Herkes | **Sadece sunucu** (guild) | Ephemeral (defer): Roblox `GET /users/{id}` ile ID doğrulanır; sonra kayıt. Aynı Roblox id başka Discord hesabına bağlıysa reddedilir. |
| `/register_username` | Herkes | Sadece sunucu | Ephemeral (defer): Roblox `POST /v1/usernames/users` ile id çözülür, sonra `/register` ile aynı kayıt ve **aynı çakışma kuralı**. **Aynı** `COOLDOWN_REGISTER_SECONDS` paylaşılır. |
| `/tasks` | Herkes | Sadece sunucu | Ephemeral embed: yalnızca **aktif** görevler; pasif görev sayısı alt bilgide (varsa). Aktif yokken pasif varsa açıklayıcı metin. |
| `/check` | Herkes | Sadece sunucu | Ephemeral: doğrulama + kredi (defer). İsteğe bağlı `gorev_id`. |
| `/nakit_talep` | Herkes | Sadece sunucu | Ephemeral: ödeme / nakit talebi kaydı; başarı mesajında limit özeti (`MAX_*`). |
| `/taleplerim` | Herkes | Sadece sunucu | Ephemeral: son nakit taleplerin (`limit` 1–15). Cooldown: `COOLDOWN_TALEPLERIM_SECONDS`. |
| `/leaderboard` | Herkes | Sadece sunucu | Ephemeral embed; `senin_siran` ile alt bilgi. |
| `/profile` | Herkes | Sadece sunucu | Ephemeral: Roblox profil linki, kredi, bekleyen talep vb. |
| `/hakkinda` | Herkes | Sadece sunucu | Ephemeral: sürüm, çalışma süresi, WS gecikmesi. |
| `/yardim` | Herkes | Sadece sunucu | Ephemeral: komut özeti. |
| `/admin …` | **Sadece** `DISCORD_ADMIN_IDS` | Sadece sunucu | Ephemeral / defer. `DISCORD_ADMIN_IDS` boşsa tüm `/admin` reddedilir. |

DM’de slash yazılabilir; kullanıcı komutları (`/register`, `/register_username`, `/tasks`, `/check`, `/yardim`, vb.) “yalnızca sunucuda” mesajı ile reddedilir. `DISCORD_BANNED_IDS` içindeki kullanıcılar **sunucuda** slash komutlarını ve **prefix** komutlarını (`$temizle`, `$hey`) kullanamaz.

### Kullanıcı slash komutları (parametreler ve davranış)

- **`/yardim`** — Kısa akış ve komut listesi.

- **`/register`** `roblox_id` (zorunlu, pozitif tam sayı)  
  - Önce Roblox `GET https://users.roblox.com/v1/users/{id}` ile hesap doğrulanır; geçersiz ID’de kayıt yapılmaz.  
  - Discord hesabını bu Roblox kullanıcı ID’sine bağlar.  
  - Bu Roblox ID’si **başka bir Discord kullanıcısında** zaten kayıtlıysa işlem reddedilir (yönetim müdahalesi gerekir).  
  - **Cooldown:** `COOLDOWN_REGISTER_SECONDS` (varsayılan 30 sn).  
  - Slash **rate limit:** `RATE_LIMIT_MAX_COMMANDS` / `RATE_LIMIT_WINDOW_SECONDS`.

- **`/register_username`** `kullanici_adi` (3–60 karakter)  
  - Roblox `POST https://users.roblox.com/v1/usernames/users` ile sayısal id çözülür, ardından kayıt `/register` ile aynıdır (çift bağlama kuralı dahil).  
  - **Cooldown:** `/register` ile **aynı** sayaç (`COOLDOWN_REGISTER_SECONDS`).

- **`/tasks`**  
  - Aktif görevleri listeler; her hedef için `https://www.roblox.com/users/<id>/profile` linki gösterilir.  
  - Pasif görev varsa embed alt bilgisinde **pasif görev sayısı**; hiç aktif yokken pasif varsa kanalda kısa açıklama (yönetici tam liste için `/admin client_list`).  
  - **Cooldown:** `COOLDOWN_TASKS_SECONDS` (varsayılan 10 sn).

- **`/hakkinda`** — Paket sürümü (`gnubot.__version__`), bu oturumdaki çalışma süresi, Discord gateway gecikmesi, sunucu sayısı ve `FOLLOW_CHECK_INTERVAL_SECONDS` özeti (ephemeral).

- **`/check`** `gorev_id` (isteğe bağlı)  
  - Boş: tüm aktif görevler için doğrulama. Dolu: yalnızca `/tasks`’te görünen **görev #id** (aktif olmalı).  
  - **Yeni kredi** yalnızca burada verilir (detay önceki sürümle aynı).  
  - **Cooldown:** `COOLDOWN_CHECK_SECONDS` (varsayılan 25 sn).

- **`/nakit_talep`** `miktar`, `not_mesaji` (isteğe bağlı)  
  - Bekleyen talep oluşturur; yönetici `/admin redeem_list` / `redeem_resolve` ile işler.  
  - Başarı yanıtında **tek talep** ve **bekleyen talep** üst sınırları kısaca tekrarlanır.  
  - Limitler: `MAX_SINGLE_REDEMPTION` (0 = sadece bakiye tavanı), `MAX_PENDING_REDEMPTIONS_PER_USER`, cooldown `COOLDOWN_REDEMPTION_SECONDS`.

- **`/taleplerim`** `limit` (1–15, varsayılan 10)  
  - Kendi `redemption_requests` kayıtlarını listeler (durum, miktar, not özeti).  
  - **Cooldown:** `COOLDOWN_TALEPLERIM_SECONDS`.

- **`/leaderboard`** `limit`, `senin_siran` (bool)  
  - Ephemeral: sıralama ve krediler yalnızca komutu kullanan kullanıcıya görünür.  
  - `senin_siran=true` iken embed alt bilgisinde sıra ve bakiyen.  
  - **Cooldown:** `COOLDOWN_LEADERBOARD_SECONDS`.

- **`/profile`**  
  - Kayıt yoksa `/register` veya `/register_username` yönlendirmesi.  
  - Roblox bağlıysa **profil linki** gösterilir.  
  - **Bekleyen nakit talebi** = `pending` durumundaki talep sayısı.  
  - **Kredi alınmış görevler** = `rewarded=true` sayısı.  
  - **Nakit talep limitleri** = `MAX_SINGLE_REDEMPTION` (0 ise tek talep üst sınırı yok) ve `MAX_PENDING_REDEMPTIONS_PER_USER`.

### Yönetim: `/admin` grubu

Tüm alt komutlar `_admin_only` ile korunur: yalnızca `DISCORD_ADMIN_IDS` içindeki kullanıcılar. Sunucu rolü veya “Yönetici” izni tek başına yetmez (bilinçli tasarım).

| Alt komut | Parametreler | Ne yapar |
|-----------|----------------|----------|
| **`/admin client_add`** | `roblox_target_id`, `target_followers`, `display_name` (isteğe bağlı) | Roblox’ta kullanıcıyı doğrular; anlık takipçi sayısını çeker; yeni görev (`client`) ekler. `current_followers` Roblox’tan, `active` hedefe göre ayarlanır. |
| **`/admin client_list`** | `active_only` (bool, varsayılan false) | Tüm veya sadece aktif görevleri listeler (en fazla 40 satır + özet). |
| **`/admin client_get`** | `client_id` | Tek görev: görünen ad, Roblox hedef + profil linki, takipçi ilerlemesi, oluşturulma (UTC). |
| **`/admin client_set_active`** | `client_id`, `active` | Görevi manuel aktif/pasif yapar (otomatik kapanışa ek olarak). |
| **`/admin client_set_target`** | `client_id`, `target_followers` | Hedef takipçi sayısını günceller; `current_followers` ile karşılaştırılıp **aktif/pasif** yeniden hesaplanır. |
| **`/admin client_rename`** | `client_id`, `display_name` (isteğe bağlı) | Kısa görünen adı yazar; parametre boş/verilmezse isim kaldırılır (`/tasks` listesinde Roblox ID kullanılır). |
| **`/admin client_refresh_followers`** | `client_id` | Yalnız bu görev için Roblox’tan takipçi sayısını çeker; `current_followers` ve **aktif/pasif** güncellenir (tüm kullanıcı senkronu değil). |
| **`/admin sync_now`** | — | Arka plan döngüsüyle aynı **toplu senkron**: müşteri takipçi sayıları, tüm kullanıcılar için takip durumu ve **takipten çıkış cezası**. **Yeni kredi (+) vermez**; pozitif kredi yalnızca kullanıcının `/check` komutuyla talep edilir. |
| **`/admin user_setpoints`** | `discord_user`, `points` | İlgili kullanıcı için `points` (kredi bakiyesi) alanını doğrudan yazar (moderasyon). |
| **`/admin user_lookup`** | `discord_user` | Roblox ID, profil linki, kredi, takip özetleri, bekleyen nakit talebi; **son 3 nakit talebi** (id / durum / miktar). |
| **`/admin user_unlink`** | `discord_user` | Roblox bağını kaldırır; ilgili `follow_history` satırlarını siler (kredi ve eski talep kayıtları korunur). |
| **`/admin redeem_list`** | `durum`, `limit` | Nakit taleplerini listeler (`durum`: pending / approved / rejected veya boş = son kayıtlar). Her satırda UTC **oluşturma**; onaylı/ret için **çözüm** zamanı ve **işlem yapan** admin mention (varsa). |
| **`/admin redeem_get`** | `talep_id` | Tek talep: kullanıcı mention, durum, miktar, anlık bakiye, notlar, çözüm zamanı ve işlem yapan admin. |
| **`/admin redeem_resolve`** | `talep_id`, `onayla`, `admin_notu` | Talebi onayla (`onayla=true`, bakiyeden düşer) veya reddet. Onay anında bakiye yetersizse talep otomatik reddedilir. |
| **`/admin stats`** | — | Kullanıcı / toplam kredi / görev (**aktif + pasif**) / `follow_history` **toplam satır + ödüllendirilmiş (`rewarded`) sayısı** / Roblox çakışma (detay: `/admin roblox_collisions`) / bekleyen talep **adet + kredi** / onaylanmış talepler **kayıt sayısı + toplam kredi** / reddedilmiş talepler **kayıt sayısı + talep edilen kredi toplamı**; Discord WS; Roblox RTT. |
| **`/admin roblox_collisions`** | `max_grup` (1-40, varsayılan 20) | Aynı Roblox ID’ye bağlı tüm Discord hesaplarını mention ile listeler (indeks / veri temizliği için). |
| **`/admin reload_config`** | — | `get_settings` önbelleğini temizleyip `.env` / ortamdan ayarları yeniden okur; bot üzerinde `settings`, hız limiti, prefix ve **Roblox HTTP oturumu** (timeout, yeniden deneme, TTL önbellek) güncellenir. Takip döngüsü aralığı bir sonraki uyku adımından itibaren yeni değeri kullanır. `DATABASE_URL` ve `DISCORD_TOKEN` yalnızca süreç yeniden başlatılarak değişir. |

**Kredi mantığı (kısa):** Aynı `(Discord kullanıcısı, görev)` için **en fazla bir kez** pozitif kredi (`FOLLOW_REWARD_POINTS`), yalnızca **`/check`** ile ve Roblox’ta takip doğrulandığında. Arka plan döngüsü takip durumunu günceller ve ödül sonrası takipten çıkışta **ceza** uygular; tekrar takip ederek sınırsız +kredi alınamaz (`rewarded` bayrağı).

Yakalanmayan slash hatalarında bot, ephemeral kısa mesaj + log dener (`GnuChanBot._handle_app_command_error`).

Yakalanmayan **prefix** komut hatalarında (ör. `$temizle`, `$hey`) bot, silinen kısa bir kanal mesajı + log dener (`GnuChanBot.on_command_error`). Bilinmeyen komut adı için mesaj gönderilmez (`CommandNotFound`).

| Komut | Yetki | Kullanım |
|--------|--------|----------|
| **`$temizle`** | Kanalda **Mesajları Yönet** | `$temizle hepsi` — kanalı 100’lük gruplarla temizler. `$temizle <sayı>` — son N mesaj (+ komut mesajı). |
| **`$hey`** | Ses kanalı + (müzik için) botun bağlanma izni | Alt komutlar: `gel` (ses kanalına katıl), `git`, `oynat <youtube url>`, `gec`, `durdur`, `liste`. `yt-dlp` ve isteğe bağlı `FFMPEG_PATH` gerekir. |

### Arka planda ne olur (komut değil ama davranış)

- **`FOLLOW_CHECK_INTERVAL_SECONDS`** (varsayılan 120 sn): Her döngü başında değer bot ayarlarından okunur ( `/admin reload_config` sonrası bir sonraki uyku adımında yeni süre uygulanır). Müşteri hesaplarının **takipçi sayısı** güncellenir; görev hedefi dolunca pasiflenir. Kayıtlı kullanıcılar için Roblox **takip listesi** çekilir; **takip durumu** (`currently_following`) senkronize edilir ve **takipten çıkış cezası** işlenir. **Pozitif kredi (+) burada eklenmez** — kullanıcı `/check` ile talep eder.  
- Roblox HTTP istekleri `User-Agent: gnuChanBOT/<sürüm> (...)` ve `Accept: application/json` ile gider (Roblox public API için iyi uygulama). Hatalarda yeniden deneme ve kısa süreli cache (`ROBLOX_CACHE_TTL_SECONDS`).

### `.env` ile ilişkili ayarlar (komut davranışı)

| Değişken | Slash davranışına etkisi |
|----------|---------------------------|
| `DISCORD_ADMIN_IDS` | Tam yetkili admin Discord ID listesi (`/admin`). Boşsa admin komutları kapalı. |
| `DISCORD_BANNED_IDS` | Slash ve prefix komutlarını sunucuda kullanması engellenen Discord ID’ler (virgülle ayrılmış). |
| `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_MAX_COMMANDS` | Kullanıcı slash komut hızı (follow cog). |
| `COOLDOWN_REGISTER_SECONDS`, `COOLDOWN_TASKS_SECONDS`, `COOLDOWN_LEADERBOARD_SECONDS`, `COOLDOWN_CHECK_SECONDS`, `COOLDOWN_REDEMPTION_SECONDS`, `COOLDOWN_TALEPLERIM_SECONDS` | İlgili slash komut bekleme süreleri. |
| `FOLLOW_REWARD_POINTS` | Yalnızca **`/check`** ile takip doğrulanınca eklenen kredi miktarı. |
| `FOLLOW_PENALTY_POINTS` | Ödül sonrası takipten çıkış cezası (`/check` veya arka plan senkronu). |
| `MAX_SINGLE_REDEMPTION`, `MAX_PENDING_REDEMPTIONS_PER_USER` | `/nakit_talep` limitleri (`MAX_SINGLE_REDEMPTION=0` → tek talepte yalnızca bakiye tavanı). |
| `DISCORD_GUILD_ID` (isteğe bağlı) | Geliştirme için slash’ları tek sunucuya hızlı sync; boşsa global sync. |

## Operations

- `DISCORD_BANNED_IDS` ve çoğu `.env` değişkeni: tam süreç yeniden başlatmadan **`/admin reload_config`** ile okunabilir (ban listesi, cooldown’lar, takip aralığı, Roblox timeout/retry/cache TTL vb.). **`DATABASE_URL`** ve **`DISCORD_TOKEN`** için güvenli tam uygulama süreç yeniden başlatmasıdır.
- Tune `FOLLOW_CHECK_INTERVAL_SECONDS` to balance Roblox API load vs freshness.
- Set `LOG_LEVEL=DEBUG` temporarily for troubleshooting.
- Admins are controlled only by numeric Discord user IDs in `DISCORD_ADMIN_IDS` (not by server roles), for consistent security across guilds.
- Bot **READY** sonrası ve her başarılı **arka plan takip döngüsünde** (`follow_checker_loop`) ile görev sayısını etkileyen **`/admin`** işlemlerinden sonra (`client_add`, `client_set_active`, `client_set_target`, `client_refresh_followers`, `sync_now`) veritabanından **aktif görev sayısı** okunup Discord “watching” durumu güncellenir (`refresh_presence`, arka planda `asyncio.create_task`).

## Production notes

- İlk açılışta (`init_schema`): **SQLite** için `PRAGMA journal_mode=WAL` ve `synchronous=NORMAL` (eşzamanlı yazımlarda daha iyi davranış). Ardından `users(roblox_id)` üzerinde `WHERE roblox_id IS NOT NULL` kısmi **benzersiz indeks** oluşturulmaya çalışılır (`IF NOT EXISTS`). **PostgreSQL** için yalnızca indeks adımı uygulanır. Çakışan Roblox satırları varsa indeks atlanır; logda uyarı — veriyi düzeltip botu yeniden başlat.
- Prefer PostgreSQL for concurrent writes and backups.
- **SQLite yedek:** Bot dururken `*.sqlite` dosyasını kopyalamak en güvenlisi; çalışırken WAL kullanıldığı için tek dosya kopyası tutarsız olabilir — SQLite `VACUUM INTO` / `.backup` veya `sqlite3` CLI `.backup` komutu tercih edilir.
- Put the bot behind a process manager (systemd, supervisord) or use Docker `restart: unless-stopped`.
- Rotate `DISCORD_TOKEN` if leaked; never commit `.env`.
