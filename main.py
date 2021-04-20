import os

import discord
from dotenv import load_dotenv
from discord.ext import commands
import aiohttp
from io import BytesIO

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix='!')

class Step(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def s(self, ctx, *args):
        year = args[0]
        paper = args[1]
        question = args[2]
        url = f"https://stepdatabase.maths.org/database/db/{year}/{year}-S{paper}-Q{question}.png"

        embed=discord.Embed(title="", description="", color=0x00484F)
        embed.add_field(name="Year", value=year, inline=True)
        embed.add_field(name="Paper", value=f"S{paper}", inline=True)
        embed.add_field(name="Question", value=f"Q{question}",inline=True)
        await ctx.send(embed=embed)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.channel.send('Could not find question...')
                data = BytesIO(await response.read())
                await ctx.send(file=discord.File(data, filename=f"SPOILER_{year}-S{paper}-Q{question}.png"))

bot.add_cog(Step(bot))
bot.run(TOKEN)