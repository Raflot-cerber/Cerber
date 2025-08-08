import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Important pour gérer les rôles et membres

bot = commands.Bot(command_prefix="!", intents=intents)

utilisateurs_deja_annonces = set()
votes_en_cours = {}  # message_id : { "user_id_candidat": int, "message_vote": message objet }

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.name == "nouveaux-arrivants👋":
        if message.author.id not in utilisateurs_deja_annonces:
            utilisateurs_deja_annonces.add(message.author.id)

            channel_liste = discord.utils.get(message.guild.channels, name="liste📜")
            if channel_liste:
                texte = (
                    f"Oyé oyé ! {message.author.display_name} frappe à la porte pour rejoindre la meute !\n"
                    "La décision est désormais entre vos mains : si la majorité l’accepte, il pourra intégrer nos rangs.\n\n"
                    "Voici un petit message de sa part :\n"
                    f"« {message.content} »\n\n"
                    "N’hésitez pas à le contacter pour en apprendre davantage sur lui !\n\n"
                    "Réagissez avec 👍 pour accepter, ou 👎 pour refuser."
                )
                msg_vote = await channel_liste.send(texte)

                # Ajout des réactions pour voter
                await msg_vote.add_reaction("👍")
                await msg_vote.add_reaction("👎")

                # On garde en mémoire le message de vote et l'ID du candidat
                votes_en_cours[msg_vote.id] = {
                    "user_id_candidat": message.author.id,
                    "message_vote": msg_vote,
                    "guild": message.guild
                }

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    # Ignorer les réactions du bot lui-même
    if user == bot.user:
        return

    msg = reaction.message

    # Vérifier si c'est un message de vote en cours
    if msg.id in votes_en_cours:
        if str(reaction.emoji) not in ["👍", "👎"]:
            return  # On s'intéresse qu'aux votes

        guild = votes_en_cours[msg.id]["guild"]
        candidat_id = votes_en_cours[msg.id]["user_id_candidat"]

        # Récupérer le rôle "Membre de la Meute"
        role_meute = discord.utils.get(guild.roles, name="Membre de la Meute")
        if role_meute is None:
            print("Le rôle 'Membre de la Meute' n'existe pas.")
            return

        # Récupérer les membres qui ont ce rôle
        membres_meute = [m for m in guild.members if role_meute in m.roles]

        # Compter les réactions sur le message de vote
        reaction_approve = discord.utils.get(msg.reactions, emoji="👍")
        reaction_reject = discord.utils.get(msg.reactions, emoji="👎")

        count_approve = 0
        count_reject = 0

        if reaction_approve:
            users_approve = await reaction_approve.users().flatten()
            count_approve = sum(1 for u in users_approve if u in membres_meute)

        if reaction_reject:
            users_reject = await reaction_reject.users().flatten()
            count_reject = sum(1 for u in users_reject if u in membres_meute)

        # Condition pour accepter : majorité des votes pour
        total_votes = count_approve + count_reject

        # On attend au moins 3 votes pour statuer (tu peux changer)
        if total_votes >= 3:
            if count_approve > count_reject:
                guild = votes_en_cours[msg.id]["guild"]
                candidat = guild.get_member(candidat_id)
                if candidat is None:
                    await msg.channel.send("Erreur : Candidat introuvable.")
                    del votes_en_cours[msg.id]
                    return

                if role_meute not in candidat.roles:
                    await candidat.add_roles(role_meute)
                    await msg.channel.send(
                        f"🎉 {candidat.display_name} a été accepté dans la meute et a reçu le rôle **Membre de la Meute** !"
                    )
                else:
                    await msg.channel.send(f"{candidat.display_name} a déjà le rôle **Membre de la Meute**.")

                # On supprime ce vote
                del votes_en_cours[msg.id]

            elif count_reject >= count_approve:
                await msg.channel.send("Le candidat n'a pas été accepté par la majorité.")
                del votes_en_cours[msg.id]

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

bot.run(TOKEN)
