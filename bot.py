import discord
from discord.ext import commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


bot.run("TON_TOKEN")
