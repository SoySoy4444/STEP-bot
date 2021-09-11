import os

import discord
from dotenv import load_dotenv
from discord.ext import commands
import aiohttp
from io import BytesIO
import psycopg2
import time, asyncio
import re

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')

conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

LATEST_YEAR = 2018

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

def process_input(question): #Union[str, Tuple[str]] -> Union[List[str], False]
    if len(question) == 1:
        question = question[0]
    if isinstance(question, str):
        question = question.replace("-", " ")
        question = question.replace("/", " ")
        question = question.split(" ")
    try:
        year, paper, q = question
    except ValueError: #incorrect number of args
        return False

    #alternatively, could use Python 3.9's str.removeprefix() method to remove S/s and Q/q specifically
    # e.g. paper = paper.removeprefix("S")
    paper = re.sub("[^0-9]", "", paper) #substitute all non-numerals with empty string e.g. get rid of S in S3
    q = re.sub("[^0-9]", "", q) #get rid of Q in Q14

    try:
        paper = int(paper)
        q = int(q)

        if year.lower() == "spec":
            if 1 <= paper <= 3 and 1 <= q <= 16:
                return ["Spec", paper, q]
            else:
                return False
        else:
            year = int(year) #year might raise error value if non numerical entered

            # if user entered shorthand year (e.g. 01 instead of 2001), then fix:
            max_year = int(str(LATEST_YEAR)[-2:]) #latest year on STEP database is 2018 as of 04/22/2021
            if 0 <= year <= max_year: #years 20000-max_year e.g. 00-18
                year += 2000
            elif 87 <= year <= 99: #years 1987 - 1999
                year += 1900

            #STEP 1 has been discontinued from 2019
            if not ((1987 <= year <= 2018 and 1 <= paper <= 3) or (2019 <= year <= LATEST_YEAR and 2 <= paper <= 3)): #valid year and paper?
                return False
            elif (year >= 2008 and q > 13) or (year >= 1994 and q > 14) or (year <= 1993 and q > 16): #valid question?
                return False

    except ValueError:
        return False

    return list(map(str, [year, paper, q]))

class Step(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current = []

    async def check_listeners(self): #clear reactions after 3600 seconds
        i = 0
        for start_time in [listener.time for listener in self.current]:
            if time.time() - start_time > 3600:
                i += 1

        for listener in self.current[:i]:
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
        if k := process_input(args):
            year, paper, question = k
        else:
            return await ctx.channel.send("Invalid arguments")

        if year == "Spec":
            url = f"https://stepdatabase.maths.org/database/db/Spec/Spec-S{paper}-Q{question}.png"
        else:
            _year = year[-2:] #last two digits of the year e.g. 01 from 2001
            url = f"https://stepdatabase.maths.org/database/db/{_year}/{_year}-S{paper}-Q{question}.png"

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
        # year, paper, question = process_input(args)
        if k := process_input(args):
            year, paper, question = k
        else:
            return await ctx.channel.send("Invalid arguments")

        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id, ))
                a = cur.fetchone()

                if f"{year} {paper} {question}" not in a[0]: #if user has not already completed the paper
                    cur.execute("UPDATE members SET completed = %s WHERE id = %s", (a[0]+f"({year} {paper} {question})", ctx.author.id))
                    await ctx.send(f"{year} S{paper} Q{question} has been marked as complete for {ctx.author.name}.")
                else:
                    await ctx.send(f"{year} S{paper} Q{question} is already complete for {ctx.author.name}.")

    @commands.command(aliases=["uc"])
    async def uncomplete(self, ctx, *args):
        if k := process_input(args):
            year, paper, question = k
        else:
            return await ctx.channel.send("Invalid arguments")

        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id, ))
                a = cur.fetchone()

                if f"{year} {paper} {question}" in a[0]: #if user has already completed the paper
                    cur.execute("UPDATE members SET completed = %s WHERE id = %s", (a[0].replace(f"({year} {paper} {question})",""), ctx.author.id))
                    await ctx.send(f"{year} S{paper} Q{question} has been marked as incomplete for {ctx.author.name}.")
                else:
                    await ctx.send(f"{year} S{paper} Q{question} is already incomplete for {ctx.author.name}.")

    @commands.command(alises=["show", "a"])
    async def show(self, ctx, *args):
        with conn: #automatically conn.commit()
            with conn.cursor() as cur: #automatically cur.close()
                cur.execute("SELECT completed FROM members WHERE id = %s", (ctx.author.id,))
                completed_str = cur.fetchone()[0]
        #e.g. ['(1999 2 5', '2004 3 1', '2001 3 2', '2009 1 12)'] - list of strings, first and last item contains ( )
        temp = completed_str[0:].split(")(")
        #remove ( and ), then for each string, split it by space then make it a tuple
        temp = [tuple(s.replace(")", "").replace("(", "").split()) for s in temp]
        #convert from list of tuples of string to list of tuples of integers
        res = [tuple(map(int, s)) for s in temp if s[0] != "Spec"]
        #sort by first (year), second (paper), third (question)
        res = sorted(res)

        spec = [("Spec", int(s[1]), int(s[2])) for s in temp if s[0] == "Spec"]
        sorted_spec = sorted(spec, key=lambda x: (x[1], x[2])) #sort by x[1] (paper) then x[2] (question)

        res += sorted_spec

        await ctx.send(res)

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