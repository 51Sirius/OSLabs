import os
import sys
import errno
from fuse import FUSE, Operations
import discord
from discord.ext import commands
from consts import *

class DiscordFUSE(Operations):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        self.client = commands.Bot(command_prefix="!", intents=intents)
        self.client.loop.create_task(self.init_bot())
        self.channels = {}
        
    async def init_bot(self):
        await self.client.wait_until_ready()
        guild = self.client.get_guild(GUILD_ID)
        root_channel = guild.get_channel(ROOT_CHANNEL_ID)
        
        if not root_channel or not isinstance(root_channel, discord.TextChannel):
            print("Invalid root channel ID or the channel is not a text channel.")
            sys.exit(1)
        
        # Create channels dictionary for root channel
        self.channels = {channel.name: channel for channel in guild.channels if isinstance(channel, discord.TextChannel) and channel.category_id == root_channel.category_id}

    def readdir(self, path, fh):
        return ['.', '..'] + [channel for channel in self.channels]

    def mkdir(self, path, mode):
        channel_name = os.path.basename(path)
        if channel_name in self.channels:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)
        
        guild = self.client.get_guild(GUILD_ID)
        root_channel = guild.get_channel(ROOT_CHANNEL_ID)
        category = root_channel.category
        
        if category:
            self.client.loop.create_task(guild.create_text_channel(channel_name, category=category))
            self.channels[channel_name] = None  # Placeholder until channel is actually created
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    def getattr(self, path, fh=None):
        st = dict(st_mode=(os.stat.S_IFDIR | 0o755), st_nlink=2)
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
