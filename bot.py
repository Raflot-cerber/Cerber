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
        await ctx.send(
            "❌ Salon `evenements` introuvable. Créez d'abord un salon `evenements`."
        )
        return

    checked = 0
    posted = 0
    deleted = 0

    # Parcours tous les salons de type "gestion-<slug>"
    gestion_channels = [c for c in guild.text_channels if c.name.startswith("gestion-")]
    for gestion in gestion_channels:
        group_slug = gestion.name[len("gestion-") :]  # ex: "les-loups"
        expected_role_slug = f"groupe-{group_slug}".lower()

        # Recherche du rôle correspondant en normalisant (minuscules + espaces -> '-')
        target_role = None
        for r in guild.roles:
            normalized = r.name.lower().replace(" ", "-")
            if normalized == expected_role_slug:
                target_role = r
                break
        if target_role is None:
            # Aucun rôle trouvé pour ce slug, on passe
            continue

        # Liste des membres du groupe
        members_in_group = [m for m in guild.members if target_role in m.roles]
        member_count = len(members_in_group)
        if member_count == 0:
            continue

        # Analyse des messages récents dans le salon de gestion
        try:
            async for message in gestion.history(limit=200):
                # On ne traite que les messages postés par le bot (propositions)
                if message.author != bot.user:
                    continue

                # Ignore s'il n'y a pas de réactions
                if not message.reactions:
                    continue

                # Récupération des réactions ✅ et ❌ (si présentes)
                yes_reaction = discord.utils.get(message.reactions, emoji="✅")
                no_reaction = discord.utils.get(message.reactions, emoji="❌")

                # Si aucune des deux, on ignore
                if not yes_reaction and not no_reaction:
                    continue

                # Compter les votes uniquement parmi les membres du groupe (et non-bots)
                yes_votes = 0
                no_votes = 0

                if yes_reaction:
                    async for u in yes_reaction.users():
                        if u.bot:
                            continue
                        if target_role in u.roles:
                            yes_votes += 1

                if no_reaction:
                    async for u in no_reaction.users():
                        if u.bot:
                            continue
                        if target_role in u.roles:
                            no_votes += 1

                # Vérifications selon ta règle : approve si yes >= member_count/2, reject si no > member_count/2
                if yes_votes >= (member_count / 2):
                    # Récupère le texte de la proposition (embed ou contenu)
                    if message.embeds:
                        description = message.embeds[0].description or message.content
                    else:
                        description = message.content or ""

                    # Détermine le nom d'affichage du groupe (préférer le nom du rôle si possible)
                    if target_role.name.lower().startswith("groupe "):
                        display_group_name = target_role.name[len("groupe ") :]
                    else:
                        display_group_name = target_role.name

                    # Poste dans evenements (avec embed propre)
                    embed = discord.Embed(
                        title=f"Nouvel événement validé pour le groupe {display_group_name}",
                        description=description,
                        color=discord.Color.green(),
                    )
                    try:
                        new_msg = await evenements_channel.send(embed=embed)
                        await new_msg.add_reaction("✅")
                        await new_msg.add_reaction("❌")
                    except discord.Forbidden:
                        await ctx.send(
                            f"⚠️ Je n'ai pas la permission d'envoyer des messages dans #{evenements_channel.name}."
                        )
                        # On ne supprime pas le message si on ne peut pas poster
                        continue
                    # Supprime le message d'origine dans gestion
                    try:
                        await message.delete()
                    except discord.Forbidden:
                        await ctx.send(
                            f"⚠️ Je n'ai pas la permission de supprimer un message dans {gestion.mention}."
                        )
                    posted += 1
                    checked += 1

                elif no_votes > (member_count / 2):
                    # Supprime la proposition rejetée
                    try:
                        await message.delete()
                    except discord.Forbidden:
                        await ctx.send(
                            f"⚠️ Je n'ai pas la permission de supprimer un message dans {gestion.mention}."
                        )
                    deleted += 1
                    checked += 1

        except Exception as e:
            # Pour éviter que toute la commande plante sur une erreur inattendue
            print(f"Erreur pendant l'analyse du salon {gestion.name}: {e}")
            continue

    await ctx.send(
        f"✅ Update terminé — {checked} messages vérifiés, {posted} postés, {deleted} supprimés."
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
