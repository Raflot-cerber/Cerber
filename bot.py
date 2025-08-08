import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")


def has_group_role(member):
    # Cherche un rôle qui commence par "groupe "
    return any(role.name.startswith("groupe ") for role in member.roles)


@bot.command()
async def groupe(ctx, nom: str, couleur: discord.Colour):
    member = ctx.author
    guild = ctx.guild

    if has_group_role(member):
        await ctx.send(
            "Tu fais déjà partie d'un groupe. Impossible d'en créer un autre."
        )
        return

    # Créer un nouveau rôle avec la couleur donnée
    try:
        nouveau_role = await guild.create_role(name=f"groupe {nom}", colour=couleur)
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de créer un rôle.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"Erreur lors de la création du rôle : {e}")
        return

    # Ajouter le rôle au membre qui a créé le groupe
    await member.add_roles(nouveau_role)

    # Créer une catégorie pour organiser les salons du groupe
    categorie = await guild.create_category(f"Groupe {nom}")

    # Permissions générales : personne sauf groupe et admins ne voit rien
    overwrites_base = {
        guild.default_role: discord.PermissionOverwrite(
            read_messages=False, send_messages=False, connect=False
        ),
    }

    # Permissions du groupe sur les salons "groupe" et "vocal"
    overwrites_groupe = overwrites_base.copy()
    overwrites_groupe.update(
        {
            nouveau_role: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, connect=True, speak=True
            ),
        }
    )

    # Permissions du groupe sur le salon "Gestion" (lecture seule)
    overwrites_gestion = overwrites_base.copy()
    overwrites_gestion.update(
        {
            nouveau_role: discord.PermissionOverwrite(
                read_messages=True, send_messages=False
            ),
        }
    )

    # Ajout des admins sur tous les salons
    for role in guild.roles:
        if role.permissions.administrator or role.permissions.manage_channels:
            overwrites_groupe[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, connect=True, speak=True
            )
            overwrites_gestion[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            )

    # Création des salons
    vocal = await guild.create_voice_channel(
        f"vocal {nom}", category=categorie, overwrites=overwrites_groupe
    )
    texte_groupe = await guild.create_text_channel(
        f"groupe {nom}", category=categorie, overwrites=overwrites_groupe
    )
    gestion = await guild.create_text_channel(
        f"Gestion {nom}", category=categorie, overwrites=overwrites_gestion
    )

    await ctx.send(
        f"Groupe '{nom}' créé avec succès ! Rôle, salons vocaux et textuels sont prêts."
    )


@bot.command()
async def leave(ctx):
    member = ctx.author
    # Trouve le rôle de groupe actuel
    role_groupe = None
    for role in member.roles:
        if role.name.startswith("groupe "):
            role_groupe = role
            break

    if role_groupe is None:
        await ctx.send("Tu ne fais partie d'aucun groupe.")
        return

    await member.remove_roles(role_groupe)
    await ctx.send(f"Tu as quitté le groupe **{role_groupe.name[7:]}**.")


@bot.command()
async def join(ctx, *, nom_groupe: str):
    member = ctx.author
    guild = ctx.guild

    # Cherche le rôle du groupe demandé (nom exact après "groupe ")
    role_demande = discord.utils.get(guild.roles, name=f"groupe {nom_groupe}")

    if role_demande is None:
        await ctx.send(f"Le groupe '{nom_groupe}' n'existe pas.")
        return

    # Vérifie le nombre de membres dans ce groupe
    membres_groupe = [m for m in guild.members if role_demande in m.roles]
    if len(membres_groupe) >= 10:
        await ctx.send("Ce groupe est complet (10 membres max).")
        return

    # Trouve l'ancien rôle de groupe de l'utilisateur
    ancien_role = None
    for role in member.roles:
        if role.name.startswith("groupe "):
            ancien_role = role
            break

    # Enlève l'ancien groupe si existe
    if ancien_role is not None:
        await member.remove_roles(ancien_role)

    # Ajoute le nouveau rôle
    await member.add_roles(role_demande)
    await ctx.send(f"Tu as rejoint le groupe **{nom_groupe}**.")


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")


bot.run(TOKEN)
