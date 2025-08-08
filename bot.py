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


@bot.command()
@commands.has_role("Membre de la Meute")
async def update(ctx):
    guild = ctx.guild
    evenements_channel = discord.utils.get(guild.text_channels, name="evenements")
    if evenements_channel is None:
        await ctx.send("Salon #evenements introuvable.")
        return

    count_checked = 0
    count_posted = 0
    count_deleted = 0

    for gestion_channel in guild.text_channels:
        if not gestion_channel.name.startswith("gestion-"):
            continue

        nom_groupe = gestion_channel.name[len("gestion-") :]
        role_groupe = discord.utils.get(guild.roles, name=f"groupe-{nom_groupe}")
        if role_groupe is None:
            continue

        membres_groupe = [m for m in guild.members if role_groupe in m.roles]
        nb_membres = len(membres_groupe)
        if nb_membres == 0:
            continue

        async for message in gestion_channel.history(limit=50):
            if message.author == bot.user:
                reactions = {str(r.emoji): r.count - 1 for r in message.reactions}
                votes_pour = reactions.get("✅", 0)
                votes_contre = reactions.get("❌", 0)

                if votes_pour >= nb_membres / 2:
                    # Message validé : poste dans evenements et ajoute réactions
                    sent_message = await evenements_channel.send(
                        f"Nouvel événement validé pour le groupe **{nom_groupe}** :\n\n{message.content}"
                    )
                    await sent_message.add_reaction("✅")
                    await sent_message.add_reaction("❌")

                    await message.delete()
                    count_posted += 1
                elif votes_contre > nb_membres / 2:
                    # Message rejeté : supprime le message
                    await message.delete()
                    count_deleted += 1

                count_checked += 1

    await ctx.send(
        f"Vérification terminée : {count_checked} messages analysés, {count_posted} validés, {count_deleted} supprimés."
    )


@bot.command()
async def event(ctx, *, message: str):
    # Vérifie si on est dans un salon texte commençant par "groupe-"
    if not ctx.channel.name.startswith("groupe-"):
        await ctx.send("❌ Cette commande doit être utilisée dans un salon de groupe.")
        return

    guild = ctx.guild
    # Récupère le nom de base du groupe (après "groupe-")
    group_slug = ctx.channel.name.replace("groupe-", "", 1)

    # Cherche le salon gestion correspondant
    gestion_channel = discord.utils.get(
        guild.text_channels, name=f"gestion-{group_slug}".lower()
    )

    if gestion_channel is None:
        await ctx.send("❌ Impossible de trouver le salon de gestion du groupe.")
        return

    # Envoie le message formaté dans "gestion-..."
    embed = discord.Embed(
        title="📢 Un nouvel événement a été proposé !",
        description=f"« {message} »\n\n"
        "Si cet événement vous plaît, votez pour sa création ! Faites vite, "
        "afin qu’il soit disponible avant notre prochain rendez-vous.\n\n"
        "Rappel : une majorité pour valide l’événement, une majorité contre le supprime.",
        color=discord.Color.gold(),
    )
    event_message = await gestion_channel.send(embed=embed)

    # Ajoute les réactions pour voter
    await event_message.add_reaction("✅")
    await event_message.add_reaction("❌")

    await ctx.send(f"✅ Événement proposé et envoyé dans {gestion_channel.mention}")


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
