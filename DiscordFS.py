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
        print("Initializing DiscordFUSE")
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
        print("Waiting for the bot to be ready")
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

        print("Bot is ready")

    def readdir(self, path, fh):
        print(f"readdir called with path: {path}")
        channel_name = path.strip('/')
        if not channel_name:
            return ['.', '..'] + [channel for channel in self.channels] + \
                   [file for file in self.messages[self.root_channel.name]]
        elif channel_name in self.channels:
            return ['.', '..'] + [file for file in self.messages[self.root_channel.name]]

    def mkdir(self, path, mode):
        print(f"mkdir called with path: {path}, mode: {mode}")
        channel_name = os.path.basename(path)
        if channel_name in self.channels:
            print(f"Channel {channel_name} already exists")
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

        new_channel = self.loop.run_until_complete(self.category.create_text_channel(channel_name))
        self.channels[channel_name] = new_channel
        self.messages[channel_name] = {}
        print(f"Channel {channel_name} created")

    def rmdir(self, path):
        print(f"rmdir called with path: {path}")
        channel_name = os.path.basename(path)
        if channel_name not in self.channels:
            print(f"Channel {channel_name} not found")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        channel = self.channels[channel_name]

        self.loop.run_until_complete(channel.delete())
        del self.channels[channel_name]
        del self.messages[channel_name]
        print(f"Channel {channel_name} deleted")

    def getattr(self, path, fh=None):
        print(f"getattr called with path: {path}")
        st = dict(st_mode=(stat.S_IFDIR | 0o755), st_nlink=2)
        if path != '/' and os.path.basename(path) not in self.channels:
            print(f"Channel {os.path.basename(path)} not found")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        return st

    def create(self, path, mode, fi=None):
        print(f"create called with path: {path}, mode: {mode}")
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if channel_name and channel_name in self.channels:
            channel = self.channels[channel_name]
        elif not channel_name:
            channel = self.root_channel
            channel_name = channel.name
        else:
            print(f"Channel {channel_name} not found")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name in self.messages[channel_name]:
            print(f"File {file_name} already exists in channel {channel_name}")
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), path)

        file = discord.File(fp=io.BytesIO(b''), filename=file_name)
        message = self.loop.run_until_complete(channel.send(file=file))
        self.messages[channel_name][file_name] = message

        print(f"File {file_name} created in channel {channel_name}")

        return 0

    def write(self, path, data, offset, fh):
        print(f"write called with path: {path}, data length: {len(data)}, offset: {offset}")
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if channel_name and channel_name in self.channels:
            channel = self.channels[channel_name]
        elif not channel_name:
            channel = self.root_channel
            channel_name = channel.name
        else:
            print(f"Channel {channel_name} not found")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name not in self.messages[channel_name]:
            print(f"File {file_name} not found in channel {channel_name}")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        message = self.messages[channel_name][file_name]
        file_content = message.attachments[0].read()
        file_content = file_content[:offset] + data.encode() + file_content[offset + len(data):]

        new_file = discord.File(io.BytesIO(file_content), filename=file_name)
        new_message = self.loop.run_until_complete(channel.send(file=new_file))
        self.messages[channel_name][file_name] = new_message
        self.loop.run_until_complete(message.delete())

        print(f"File {file_name} written in channel {channel_name}")

    def unlink(self, path):
        print(f"unlink called with path: {path}")
        file_name = os.path.basename(path)

        channel_name = os.path.dirname(path).strip('/')
        if not channel_name:
            channel_name = self.root_channel.name
        elif channel_name not in self.channels:
            print(f"Channel {channel_name} not found")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        if file_name not in self.messages[channel_name]:
            print(f"File {file_name} not found in channel {channel_name}")
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

        message = self.messages[channel_name][file_name]
        del self.messages[channel_name][file_name]
        self.loop.run_until_complete(message.delete())

        print(f"File {file_name} deleted in channel {channel_name}")


def main(mountpoint):
    fuse = FUSE(DiscordFUSE(), mountpoint, foreground=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: {} <mountpoint>'.format(sys.argv[0]))
        sys.exit(1)
    main(sys.argv[1])
