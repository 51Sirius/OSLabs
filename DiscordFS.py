import os
import sys
import time

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
        self.channels = {}
        self.files = {}

    def getattr(self, path, fh=None):
        st = dict(st_mode=(S_IFDIR | 0o755), st_nlink=2)
        if path != '/':
            filename = path.strip('/')
            if filename in self.files:
                file_info = self.files[filename]
                st = dict(st_mode=(S_IFREG | 0o644), st_nlink=1, st_size=file_info['size'],
                          st_ctime=file_info['ctime'], st_mtime=file_info['mtime'])
            else:
                raise FileNotFoundError(f"No such file: {filename}")
        return st

    def readdir(self, path, fh):
        return ['.', '..'] + list(self.channels.keys()) + list(self.files.keys())

    def mkdir(self, path, mode):
        dirname = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.create_channel(dirname), self.loop).result()
        self.channels[dirname] = None

    def rmdir(self, path):
        dirname = path.strip('/')
        if dirname in self.channels:
            asyncio.run_coroutine_threadsafe(self.delete_channel(dirname), self.loop).result()
            del self.channels[dirname]

    def create(self, path, mode, fi=None):
        filename = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.send_message(ROOT_CHANNEL_ID, f"New file created: {filename}"),
                                         self.loop).result()

    def write(self, path, data, offset, fh):
        filename = path.strip('/')
        message = asyncio.run_coroutine_threadsafe(self.send_message(ROOT_CHANNEL_ID, data, filename=filename),
                                                   self.loop).result()
        ctime = time.mktime(message.created_at.timetuple())
        self.files[filename] = {
            'id': message.id,
            'size': len(data),
            'ctime': ctime,
            'mtime': ctime
        }
        return len(data)

    def read(self, path, size, offset, fh):
        filename = path.strip('/')
        file_info = self.files.get(filename)
        if file_info:
            content = asyncio.run_coroutine_threadsafe(self.get_message_content(ROOT_CHANNEL_ID, file_info['id']),
                                                       self.loop).result()
            return content[offset:offset + size]
        else:
            raise IOError("File not found")

    def unlink(self, path):
        filename = path.strip('/')
        asyncio.run_coroutine_threadsafe(self.delete_message(ROOT_CHANNEL_ID, filename), self.loop).result()
        del self.files[filename]

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
            file = discord.File(fp=io.BytesIO(content), filename=filename)
            message = await channel.send(file=file)
        else:
            message = await channel.send(content.decode())
        return message

    async def get_message_content(self, channel_id, message_id):
        channel = client.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        if message.attachments:
            attachment = message.attachments[0]
            content = await attachment.read()
        else:
            content = message.content.encode()
        return content

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
        loop = asyncio.get_event_loop()
        fuse_thread = threading.Thread(target=start_fuse, args=(mountpoint, loop))
        fuse_thread.start()


    client.run(TOKEN)
