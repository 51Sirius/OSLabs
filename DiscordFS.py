import os
import sys
import discord
from fuse import FUSE, Operations
import io
from stat import S_IFDIR, S_IFREG
import asyncio
from consts import *
import threading

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

client = discord.Client(intents=intents)

class DiscordFS(Operations):
    def __init__(self, loop):
        self.loop = loop
        self.channels = {}  # Сохранение каналов как директорий

    def getattr(self, path, fh=None):
        # Атрибуты файла или директории
        st = dict(st_mode=(S_IFDIR | 0o755), st_nlink=2)
        if path != '/':
            st = dict(st_mode=(S_IFREG | 0o644), st_nlink=1, st_size=100)
        return st

    def readdir(self, path, fh):
        # Чтение содержимого директории
        return ['.', '..'] + list(self.channels.keys())

    def mkdir(self, path, mode):
        # Создание новой директории (канала)
        dirname = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.create_channel(dirname), self.loop).result()
        self.channels[dirname] = None

    def rmdir(self, path):
        # Удаление директории (канала)
        dirname = path.strip('/')
        if dirname in self.channels:
            asyncio.run_coroutine_threadsafe(self.delete_channel(dirname), self.loop).result()
            del self.channels[dirname]

    def create(self, path, mode, fi=None):
        # Создание файла (отправка сообщения)
        filename = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.send_message(ROOT_CHANNEL_ID, f"New file created: {filename}"), self.loop).result()

    def write(self, path, data, offset, fh):
        # Запись данных в файл (отправка сообщения с файлом)
        filename = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.send_message(ROOT_CHANNEL_ID, data, filename=filename), self.loop).result()
        return len(data)

    def unlink(self, path):
        # Удаление файла (удаление сообщения)
        filename = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.delete_message(ROOT_CHANNEL_ID, filename), self.loop).result()

    async def create_channel(self, name):
        guild = client.get_guild(GUILD_ID)
        await guild.create_text_channel(name)

    async def delete_channel(self, name):
        guild = client.get_guild(GUILD_ID)
        channel = discord.utils.get(guild.channels, name=name)
        await channel.delete()

    async def send_message(self, channel_id, content, filename=None):
        channel = client.get_channel(channel_id)
        if filename:
            file = discord.File(fp=io.BytesIO(content.encode()), filename=filename)
            await channel.send(file=file)
        else:
            await channel.send(content)

    async def delete_message(self, channel_id, filename):
        channel = client.get_channel(channel_id)
        async for message in channel.history():
            if message.attachments and message.attachments[0].filename == filename:
                await message.delete()

def start_fuse(mountpoint, loop):
    fuse_operations = DiscordFS(loop)
    FUSE(fuse_operations, mountpoint, nothreads=True, foreground=True)

if __name__ == '__main__':
    mountpoint = sys.argv[1]

    @client.event
    async def on_ready():
        print(f'Logged in as {client.user}')

        # Запуск FUSE в отдельном потоке
        loop = asyncio.get_event_loop()
        fuse_thread = threading.Thread(target=start_fuse, args=(mountpoint, loop))
        fuse_thread.start()

    client.run(TOKEN)
