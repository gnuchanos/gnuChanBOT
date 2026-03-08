import requests
import discord
from discord.ext import commands

import json
import time
import os
import asyncio
import yt_dlp


# if you using winfart an you don't have ffmpeg di this maybe works
# $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine")

class BOTSCONTROL:
    def __init__(self):
        self.CustomerIDPOLL = []
        self.FollowerIDPOLL = []

        self.Follower = {}
        self.Customer = {}

        self.CurrentPath = os.getcwd()

        self.intents = discord.Intents.default()
        self.intents.message_content = True

        self.BOT = commands.Bot(command_prefix='$', intents=self.intents)

        self.u = {}
        self.r = {}
        self.PlaceHolderFollowerList = []
    
    def AddCustomer(self, ID: str, FinalFollower: int):
        try:
            self.r = requests.get(f"https://friends.roblox.com/v1/users/{str(ID)}/followers/count").json()
            #time.sleep(1)
        except requests.exceptions.RequestException as ERR:
            print(f"Connection error: {ERR}")
        else:
            try:
                self.u = requests.get(f"https://users.roblox.com/v1/users/{str(ID)}").json()
                #time.sleep(1)
            except requests.exceptions.RequestException as e:
                print(f"Connection error: {e}")
            else:
                if str(ID) not in self.CustomerIDPOLL:
                    self.CustomerIDPOLL.append(str(ID))

                    self.Customer[str(ID)] = {
                        "ID"            : self.u["id"],
                        "Name"          : self.u["name"],
                        "Follower"      : self.r["count"],
                        "FinalFollower" : FinalFollower,
                    }

            self.SaveCustomer()
            return f"Name: {self.u["name"]} | ID: {self.u["id"]} | Follower: {self.r["count"]} | Final Follower: {FinalFollower}"
            # https://friends.roblox.com/v1/users/3123123/followers

    def AddFollower(self, ID: str):
        self.PlaceHolderFollowerList = []

        try:
            self.r = requests.get(f"https://friends.roblox.com/v1/users/{str(ID)}/followings").json()
            #time.sleep(1)

        except requests.exceptions.RequestException as ERR:
            print(f"Connection error: {ERR}")
            return ERR
        else:
            for i in self.r["data"]:
                _PlaceHolderIDRAW = str(i).split(":")
                _PlaceHolderID = str(_PlaceHolderIDRAW[1][1:-1])
                self.PlaceHolderFollowerList.append(_PlaceHolderID)
            try:
                self.u = requests.get(f"https://users.roblox.com/v1/users/{str(ID)}").json()
            except requests.exceptions.RequestException as ERR:
                print(ERR)
                return ERR
            else:
                if str(ID) not in self.FollowerIDPOLL:
                    self.FollowerIDPOLL.append(str(ID))

                    self.Follower[str(ID)] = {
                        "ID"              : self.u["id"],
                        "Name"            : self.u["name"],
                        "FollowersList"   : self.PlaceHolderFollowerList,
                        "PointFollower"   : {},
                        "Point"           : 0,
                    }

        self.SaveFollower()
        return f"Name: {self.u["name"]} | ID: {self.u["id"]} | Point: {self.Follower[str(ID)]["Point"]} | Follower List: {self.Follower[str(ID)]["FollowersList"]}  | Point Follower {self.Follower[str(ID)]["PointFollower"]}"


    def SaveCustomer(self):
        _FileCustomer = os.path.join(self.CurrentPath, "Customer.gc")
        with open(_FileCustomer, "w", encoding="utf-8") as f:
            json.dump(self.Customer, f, indent=4)

    def SaveFollower(self):
        _FileFollower = os.path.join(self.CurrentPath, "Follower.gc")
        with open(_FileFollower, "w", encoding="utf-8") as f:
            json.dump(self.Follower, f, indent=4)

    def LoadCustomer(self):
        _FileCustomer = os.path.join(self.CurrentPath, "Customer.gc")
        with open(_FileCustomer, "r", encoding="utf-8") as f:
            self.Customer = json.load(f)

        for i in self.Customer.keys():
            self.UpdateCustomer(ID=i)

    def LoadFollower(self):
        _FileFollower = os.path.join(self.CurrentPath, "Follower.gc")
        with open(_FileFollower, "r", encoding="utf-8") as f:
            self.Follower = json.load(f)

        for i in self.Follower.keys():
            self.UpdateFollower(ID=i)
        
    def UpdateCustomer(self, ID):
        try:
            self.r = requests.get(f"https://friends.roblox.com/v1/users/{str(ID)}/followers/count").json()
            print(self.r)

        except requests.exceptions.RequestException as ERR:
            print(ERR)
            return ERR

        else:
            self.Customer[str(ID)]["Follower"] = self.r["count"]

        time.sleep(1)
        self.SaveCustomer()

    def UpdateFollower(self, ID):
        try:
            self.r = requests.get(f"https://friends.roblox.com/v1/users/{str(ID)}/followings").json()
            print(self.r)

        except requests.exceptions.RequestException as ERR:
            print(ERR)
            return ERR

        else:
            for i in self.r["data"]:
                _PlaceHolderIDRAW = str(i).split(":")
                _PlaceHolderID = str(_PlaceHolderIDRAW[1][1:-1])

                if _PlaceHolderID not in self.PlaceHolderFollowerList:
                    self.PlaceHolderFollowerList.append(_PlaceHolderID)
                    self.Follower[str(ID)]["FollowersList"] = self.PlaceHolderFollowerList
            
            # if data = 0 you can't check if un follow
            if len(self.r["data"]) == 0:
                self.Follower[str(ID)]["FollowersList"] = []

        time.sleep(1)
        self.SaveFollower()

    def FollowerDoFollow(self, FollowerID, CustomerID):
        self.LoadFollower()

        _Message0 = f"-----> Name: {self.Follower[str(FollowerID)]['Name']} | ID: {self.Follower[str(FollowerID)]['ID']} \n"
        _Message1 = ''
        _Message2 = ''
        self.PlaceHolderFollowerList = []

        if CustomerID not in self.Follower[str(FollowerID)]["PointFollower"]:
            self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)] = {}
            self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsGetPoint"]    = False
            self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["StillFollowed"] = False
            self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsFolloweBefore"] = False
            self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsGetMoney"] = False
        try:
            self.r = requests.get(f"https://friends.roblox.com/v1/users/{str(FollowerID)}/followings").json()
        except requests.exceptions.RequestException as ERR:
            print(ERR)
            return ERR
        else:
            for i in self.r["data"]:
                _PlaceHolderIDRAW = str(i).split(":")
                _PlaceHolderID = str(_PlaceHolderIDRAW[1][1:-1])

                self.PlaceHolderFollowerList.append(_PlaceHolderID)
                self.Follower[str(FollowerID)]["FollowersList"] = self.PlaceHolderFollowerList

            for i in self.PlaceHolderFollowerList:
                _Message0 += f"{i} = {CustomerID}"
                if str(i) == str(CustomerID):
                    self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["StillFollowed"] = True
                    break
                else:
                    self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["StillFollowed"] = False


            time.sleep(1)

            if len(self.PlaceHolderFollowerList) == 0:
                self.Follower[str(FollowerID)]["Point"] = 0
                return f"Kimseyi Takip etmemissin BRUH Puanin sifirlandi {self.PlaceHolderFollowerList}"

            time.sleep(1)

            if not self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsFolloweBefore"]:
                if self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["StillFollowed"]:
                    self.Follower[str(FollowerID)]["Point"] += 1
                    self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsFolloweBefore"] = True
                    _Message1 += f"ID: {str(CustomerID)} Takip Ettiği İçin Puan Kazandı +1 --> ID: {FollowerID} \n"
                else:
                    _Message1 += f"ID: {str(CustomerID)} Takip Etmedi --> ID: {FollowerID} \n"
            else:
                if self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["StillFollowed"]:
                    if not self.Follower[str(FollowerID)]["PointFollower"][str(CustomerID)]["IsGetMoney"]:
                        _Message1 += f"ID: {str(CustomerID)} Bu ID, puanından para almadan önce tekrar takip ettiği için puanı geri verildi --> ID: {FollowerID} \n"
                    else:
                        _Message1 += f"ID: {str(CustomerID)} Hâlâ Takip Ediyor --> ID: {FollowerID} \n"
                else:
                    _Message1 += f"ID: {str(CustomerID)} Takipten Çıkıldığı İçin Puan Kaybetti --> ID: {FollowerID} \n"
                    self.Follower[str(FollowerID)]["Point"] -= 1

            time.sleep(1)
        
        self.SaveFollower()

        _Message2 += f"Şu anki Puanın: {self.Follower[str(FollowerID)]['Point']}"

        FinalText = f"{_Message0} \n {_Message1} \n {_Message2} \n"
        return FinalText
    def IsStillFollowing(self):
        _Message = ""


        return _Message
    def CheckCustomerIsDONE(self):
        _Message = ""


        return _Message


if __name__ == "__main__":
    gc = BOTSCONTROL()
    _Zoken = ''
    _Path = os.path.join(os.getcwd(), "_token.gc")
    with open(file=_Path, mode='r') as f:
        _Zoken = f.read()


    @gc.BOT.event
    async def on_ready():
        gc.LoadFollower()
        gc.LoadCustomer()
        channel = gc.BOT.get_channel(1466781983127634063)
        if channel:
            await channel.send(f'{gc.BOT.user} I USE ARCH GNU/LINUX BTW')

    @gc.BOT.event
    async def on_ready():
        async def loop():
            while True:
                gc.LoadCustomer()
                gc.LoadFollower()
                channel = gc.BOT.get_channel(1466781983127634063)
                if channel:
                    await channel.send(f'{gc.BOT.user} I USE ARCH GNU/LINUX BTW')
                await asyncio.sleep(300)
        gc.BOT.loop.create_task(loop())

    time.sleep(1)

    @gc.BOT.command()
    @commands.has_permissions(manage_messages=True)
    async def temizle(ctx, arg=None):
        if not arg:
            await ctx.send("Kullanım: !temizle all | !temizle <sayı>")
            return

        # ALL
        if arg.lower() == "hepsi":
            while True:
                silinen = await ctx.channel.purge(limit=100)
                if len(silinen) < 100:
                    break

            await ctx.send("🧹 Tüm mesajlar silindi.", delete_after=3)
            return

        # SAYI
        if not arg.isdigit():
            await ctx.send("Kullanım: !temizle all | !temizle <sayı>")
            return

        sayi = int(arg)
        await ctx.channel.purge(limit=sayi + 1)
        await ctx.send(f"🧹 {sayi} mesaj silindi.", delete_after=3)

    # Takip Sistemi
    @gc.BOT.command()
    async def takipci(ctx, *args):
        if not args:
            await ctx.send("Komut belirtmedin bro.")
            return None

        command = args[0].lower()

        if command == "tara":
            if "Kurucu" not in [role.name for role in ctx.author.roles]:
                await ctx.send("❌ Bu komutu sadece **Kurucu** kullanabilir.")
                return

            msg = gc.IsStillFollowing()
            await ctx.send(msg)

        elif command == "guncelle":
            if "Kurucu" not in [role.name for role in ctx.author.roles]:
                await ctx.send("❌ Bu komutu sadece **Kurucu** kullanabilir.")
                return

            gc.LoadCustomer()
            gc.LoadFollower()
            await ctx.send("bitti!")

        elif command == "ekle":
            if len(args) < 2:
                await ctx.send("Kullanım: follower check <ID>")
                return None

            msg = gc.AddFollower(ID=args[1])
            await ctx.send(msg)
        
        elif command == "musteri":
            if "Kurucu" not in [role.name for role in ctx.author.roles]:
                await ctx.send("❌ Bu komutu kullanma yetkin yok.")
                return

            if len(args) != 3:
                await ctx.send("Kullanım: follower musteri <CustomerID> <hedef takipci>")
                return

            customer_id = args[1]
            hedef = args[2]

            msg = gc.AddCustomer(ID=customer_id, FinalFollower=hedef)
            await ctx.send(msg)
        elif command == "kontrol":
            if len(args) < 3:
                await ctx.send("Kullanım: follower add <FollowerID> <CustomerID>")
                return None

            msg = gc.FollowerDoFollow(FollowerID=args[1], CustomerID=args[2])
            await ctx.send(msg)
        
        elif command == "guncelle":
            gc.UpdateFollower()
            gc.UpdateCustomer()

        else:
            await ctx.send("Bilinmeyen komut.")


    # Music

    music_queue = []

    def play_next(ctx):
        if not music_queue:
            return

        audio_url, title = music_queue.pop(0)

        source = discord.FFmpegPCMAudio(
            audio_url,
            executable="C:/ffmpeg/bin/ffmpeg.exe"
        )

        ctx.voice_client.play(source, after=lambda e: play_next(ctx))

    @gc.BOT.command()
    async def hey(ctx, *args):
        if not args:
            await ctx.send("Komut belirtmedin bro.")
            return

        command = args[0].lower()

        if command == "gel":
            if not ctx.author.voice:
                await ctx.send("❌ Seslide değilsin.")
                return

            channel = ctx.author.voice.channel

            if ctx.voice_client:
                await ctx.send("Zaten seslideyim 😄")
                return

            await channel.connect()
            await ctx.send("🔊 Sesliye geldim.")

        elif command == "git":
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
                await ctx.send("👋 Çıktım.")
            else:
                await ctx.send("Zaten seslide değilim.")

        elif command == "oynat":
            if len(args) < 2:
                await ctx.send("Kullanım: hey oynat <youtube link>")
                return

            if not ctx.voice_client:
                if ctx.author.voice:
                    await ctx.author.voice.channel.connect()
                else:
                    await ctx.send("❌ Sesliye gir.")
                    return

            url = args[1]

            ydl_opts = {
                "format"      : "bestaudio/best",
                "quiet"       : True,
                "ignoreerrors": True,  # Skip Private Vieos
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                # Playlist ise
                if "entries" in info:
                    added = 0
                    for entry in info["entries"]:
                        if not entry:
                            continue

                        music_queue.append((entry["url"], entry["title"]))
                        added += 1

                    await ctx.send(f"📥 Playlist eklendi ({added} video)")
                else:
                    music_queue.append((info["url"], info["title"]))
                    await ctx.send(f"📥 Kuyruğa eklendi: **{info['title']}**")

                if not ctx.voice_client.is_playing():
                    play_next(ctx)

            except Exception as e:
                await ctx.send("❌ Video oynatılamıyor (private veya yasaklı).")

        elif command == "gec":
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
                await ctx.send("⏭️ Geçildi.")
            else:
                await ctx.send("Çalan yok.")

        elif command == "durdur":
            music_queue.clear()

            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()

            await ctx.send("⏹️ Durduruldu, kuyruk temizlendi.")

        elif command == "liste":
            if not music_queue:
                await ctx.send("📭 Kuyruk boş.")
                return

            i = 1
            text = ''

            for item in music_queue:
                title = item[1]
                i += 1
                text += f"{i}: {title} \n"

            await ctx.send(f"🎶 **Oynatma Listesi:**\n{text}")

        elif command == "durdur":
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
                await ctx.send("⏹️ Müzik durduruldu.")
            else:
                await ctx.send("Çalan bir şey yok.")

        else:
            await ctx.send("Bilinmeyen komut.")

    gc.BOT.run(token=_Zoken)




    #"""







