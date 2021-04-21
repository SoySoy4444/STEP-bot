import os

import discord
from dotenv import load_dotenv
from discord.ext import commands
import aiohttp
from io import BytesIO
import psycopg2
import time, asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')

conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

with conn:
    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS "members"(
                "id" BIGSERIAL,
                "completed" TEXT,
                "username" VARCHAR(100)
            )''')

bot = commands.Bot(command_prefix='!')

class ReactionContext:
    def __init__(self, author, channel):
        self.author = author
        self.channel = channel

    async def send(self, msg):
        await self.channel.send(msg)

    def __repr__(self):
        return f"{self.author}, {self.channel}"

class Listener:
    def __init__(self, k, author, message, edit, question):
        self.k = k
        self.author = author
        self.message = message
        self.edit_message = edit #Completed? <emoji>
        self.question = question #year S_paper question
        self.time = time.time()

    def __repr__(self):
        return "{}\n{}\n{}\n{}\n{}\n{}".format(self.k, self.author, self.edit_message, self.message, self.question, self.time)

class Step(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current = []

    async def check_listeners(self):
        i = 0
        for start_time in [listener.time for listener in self.current]:
            if time.time() - start_time > 300:
                i += 1

        for l in self.current[:i]:
            await listener.k.clear_reactions()
        self.current = self.current[i:]


    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot}")
        while True:
            await self.check_listeners()
            await asyncio.sleep(10)

    @commands.command()
    async def s(self, ctx, *args):
        year = args[0]
        paper = args[1]
        question = args[2]
        url = f"https://stepdatabase.maths.org/database/db/{year}/{year}-S{paper}-Q{question}.png"

        embed=discord.Embed(title="", description=f"Checking for {ctx.author}", color=0x00484F)
        embed.add_field(name="Year", value=year, inline=True)
        embed.add_field(name="Paper", value=f"S{paper}", inline=True)
        embed.add_field(name="Question", value=f"Q{question}", inline=True)
        await ctx.send(embed=embed)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.channel.send('Could not find question...')
                data = BytesIO(await response.read())
                k = await ctx.send(file=discord.File(data, filename=f"SPOILER_{year}-S{paper}-Q{question}.png"))

                await k.add_reaction("\u2705")
                await k.add_reaction("\u274C")

        with conn: #automatically conn.commit()
            with conn.cursor() as cur: #automatically cur.close()
                cur.execute('''SELECT * FROM members WHERE id = %s''', (ctx.author.id, )) # get the users with matching id (should be one)
                res = cur.fetchone()

                #Add/update users
                if res == None: # user is not in db
                    #id, completed (should be empty), username
                    cur.execute("INSERT INTO members VALUES (%s,%s,%s)", (int(ctx.author.id), "", f"{ctx.author.name}#{ctx.author.discriminator}"))
                    print(f"User {ctx.author.name}#{ctx.author.discriminator}, {ctx.author.id} added to database")
                else: #user is in db, they may have changed username so update
                    cur.execute("UPDATE members SET username = %s WHERE id = %s", (f"{ctx.author.name}#{ctx.author.discriminator}", ctx.author.id))

                #Check question completion
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id,))
                completed_str = cur.fetchone()[0]
                emoji = "\u2705" if f"{year} {paper} {question}" in completed_str else "\u274C"

                edit = await ctx.send(f"Completed? {emoji}")

        self.current.append(Listener(k, ctx.author, ctx.message, edit, f"{year} {paper} {question}"))

    @commands.command(aliases=["c"])
    async def complete(self, ctx, *args):
        try:
            year = args[0]
            paper = args[1]
            question = args[2]
        except IndexError:
            return await ctx.send("Insufficient number of arguments")
        except TypeError:
            return await ctx.send("Need arguments")

        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id, ))
                a = cur.fetchone()

                if 87 <= int(year) <= 99:
                    _year = int(year) + 1900
                elif 0 <= int(year) <= 17:
                    _year = int(year) + 2000

                if f"{year} {paper} {question}" not in a[0]: #if user has not already completed the paper
                    if (1987 <= _year <= 2018 and int(paper) in [1, 2, 3]) or (_year >= 2019 and int(paper) in [2, 3]): #STEP 1 has been discontinued from 2019
                        cur.execute("UPDATE members SET completed = %s WHERE id = %s", (a[0]+f"{year} {paper} {question}", ctx.author.id))
                        await ctx.send(f"{_year} S{paper} Q{question} has been marked as complete for {ctx.author.name}.")

    @commands.command(aliases=["uc"])
    async def uncomplete(self, ctx, *args):
        try:
            year = args[0]
            paper = args[1]
            question = args[2]
        except IndexError:
            return await ctx.send("Insufficient number of arguments")
        except TypeError:
            return await ctx.send("Need arguments")

        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id, ))
                a = cur.fetchone()

                if 87 <= int(year) <= 99:
                    _year = int(year) + 1900
                elif 0 <= int(year) <= 17:
                    _year = int(year) + 2000

                if f"{year} {paper} {question}" in a[0]: #if user has already completed the paper
                    if (1987 <= _year <= 2018 and int(paper) in [1, 2, 3]) or (_year >= 2019 and int(paper) in [2, 3]): #STEP 1 has been discontinued from 2019
                        cur.execute("UPDATE members SET completed = %s WHERE id = %s", (a[0].replace(f"{year} {paper} {question}",""), ctx.author.id))
                        await ctx.send(f"{_year} S{paper} Q{question} has been marked as uncomplete for {ctx.author.name}.")        

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        for listener in self.current:
            if user.id != bot.user.id:
                ctx = ReactionContext(user, listener.message.channel)
                if reaction.emoji == "❌" and reaction.message.id == listener.k.id:
                    await listener.k.remove_reaction("❌", user)
                    await self.uncomplete(ctx, *listener.question.split(" "))

                    #only if the user is correct, then edit the Correct? <emoji> message
                    if user.id == listener.author.id:
                        new_content = listener.edit_message.content.replace("✅", "❌")
                        await listener.edit_message.edit(content=new_content)

                elif reaction.emoji == "✅" and reaction.message.id == listener.k.id:
                    await listener.k.remove_reaction("✅", user)
                    await self.complete(ctx, *listener.question.split(" "))

                    if user.id == listener.author.id:
                        new_content = listener.edit_message.content.replace("❌", "✅")
                        await listener.edit_message.edit(content=new_content)


bot.add_cog(Step(bot))
bot.run(TOKEN)