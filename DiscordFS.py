import io
import os
import sys
import errno
import asyncio
from fuse import FUSE, Operations
import discord
from discord.ext import commands
import stat

from consts import *


class DiscordFUSE(Operations):
    def __init__(self):
        self.category = None
        self.root_channel = None
        self.channels = {}
        self.messages = {}
        self.loop = asyncio.get_event_loop()
        
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        self.client = commands.Bot(command_prefix="!", intents=intents)
        self.loop.create_task(self.client.start(TOKEN))
        
        self.loop.run_until_complete(self.init_bot())

    async def init_bot(self):
        await self.client.wait_until_ready()
        guild = self.client.get_guild(GUILD_ID)
        self.root_channel = guild.get_channel(ROOT_CHANNEL_ID)

        if not self.root_channel or not isinstance(self.root_channel, discord.TextChannel):
            print("Invalid root channel ID or the channel is not a text channel.")
            sys.exit(1)

        self.category = self.root_channel.category

        if not self.category:
            print("Root channel does not have a category.")
            sys.exit(1)

        self.channels = {channel.name: channel for channel in self.category.text_channels}
        self.messages = {channel.name: {} for channel in self.category.text_channels}

    def readdir(self, path, fh):
        channel_name = path.strip('/')
        if not channel_name:
            return ['.', '..'] + [channel for channel in self.channels] + \
                   [file for file in self.messages[self.root_channel.name]]
        elif channel_name in self.channels:
            return ['.', '..'] + [file for file in self.messages[self.channels[channel_name]]]

    def mkdir(self, path, mode):
        channel_name = os.path.basename(path)
        if channel_name in self.channels:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

        new_channel = self.loop.run_until_complete(self.category.create_text_channel(channel_name))
        self.channels[channel_name] = new_channel
        self.messages[channel_name] = {}

    def rmdir(self, path):
        channel_name = os.path.basename(path)
        if channel_name not in self.channels:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        channel = self.channels[channel_name]

        self.loop.run_until_complete(channel.delete())
        del self.channels[channel_name]
        del self.messages[channel_name]

    def getattr(self, path, fh=None):
        st = dict(st_mode=(stat.S_IFDIR | 0o755), st_nlink=2)
        if path == '/':
            return st
        parts = path.strip('/').split('/')
        if len(parts) == 1:
            if parts[0] in self.channels:
                return st
            if parts[0] in self.messages[self.root_channel.name]:
                st = dict(st_mode=(stat.S_IFREG | 0o644),
                          st_size=self.messages[self.root_channel.name][parts[0]].attachments[0].size)
                return st
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        elif len(parts) == 2:
            channel_name, file_name = parts
            if channel_name in self.channels and file_name in self.messages[channel_name]:
                st = dict(st_mode=(stat.S_IFREG | 0o644),
                          st_size=self.messages[channel_name][file_name].attachments[0].size)
                return st
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def create(self, path, mode, fi=None):
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if channel_name and channel_name in self.channels:
            channel = self.channels[channel_name]
        elif not channel_name:
            channel = self.root_channel
            channel_name = channel.name
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name in self.messages[channel_name]:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

        file = discord.File(fp=io.BytesIO(b''), filename=file_name)

        message = self.loop.run_until_complete(channel.send(file=file))
        self.messages[channel_name][file_name] = message

        return 0

    def write(self, path, data, offset, fh):
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if channel_name and channel_name in self.channels:
            channel = self.channels[channel_name]
        elif not channel_name:
            channel = self.root_channel
            channel_name = channel.name
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name not in self.messages[channel_name]:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        message = self.messages[channel_name][file_name]

        file_content = self.loop.run_until_complete(message.attachments[0].read())
        file_content = file_content[:offset] + data + file_content[offset + len(data):]

        new_file = discord.File(io.BytesIO(file_content), filename=file_name)

        new_message = self.loop.run_until_complete(channel.send(file=new_file))
        self.messages[channel_name][file_name] = new_message
        self.loop.run_until_complete(message.delete())

        return len(data)

    def unlink(self, path):
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if not channel_name:
            channel_name = self.root_channel.name
        elif channel_name not in self.channels:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name not in self.messages[channel_name]:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        message = self.messages[channel_name][file_name]

        del self.messages[channel_name][file_name]
        self.loop.run_until_complete(message.delete())


def main(mountpoint):
    fuse = FUSE(DiscordFUSE(), mountpoint, foreground=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: {} <mountpoint>'.format(sys.argv[0]))
        sys.exit(1)
    main(sys.argv[1])
