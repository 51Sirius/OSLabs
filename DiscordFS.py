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
        self.loop = asyncio.get_event_loop()
        self.client = commands.Bot(command_prefix="!", intents=intents)
        self.loop.create_task(self.client.start(TOKEN))
        self.loop.run_until_complete(self.init_bot())

    async def init_bot(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True

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

    def readdir(self, path, fh):
        if path == '/':
            return ['.', '..'] + [channel for channel in self.channels]
        else:
            return ['.', '..']

    def mkdir(self, path, mode):
        channel_name = os.path.basename(path)
        if channel_name in self.channels:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

        new_channel = self.loop.run_until_complete(self.category.create_text_channel(channel_name))
        self.channels[channel_name] = new_channel

    def rmdir(self, path):
        channel_name = os.path.basename(path)
        if channel_name not in self.channels:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        channel = self.channels[channel_name]

        self.loop.run_until_complete(channel.delete())
        del self.channels[channel_name]

    def getattr(self, path, fh=None):
        st = dict(st_mode=(stat.S_IFDIR | 0o755), st_nlink=2)
        if path != '/' and os.path.basename(path) not in self.channels:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        return st


def main(mountpoint):
    fuse = FUSE(DiscordFUSE(), mountpoint, foreground=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: {} <mountpoint>'.format(sys.argv[0]))
        sys.exit(1)
    main(sys.argv[1])
