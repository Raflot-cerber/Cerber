# -*- coding: utf-8 -*-

import json
import os
from collections import Counter
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Modal, Select, TextInput, View
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Noms des Rôles & Salons ---
ASSEMBLEE_CHANNEL_NAME = "assemblée"
EVENT_PROPOSALS_CHANNEL_NAME = "propositions-evenements"
WELCOME_CHANNEL_NAME = "bienvenue-lis-moi"
RECOMMENDERS_CHANNEL_NAME = "qui-peut-me-recommander"
LOG_CHANNEL_NAME_ADMIN = "bot-logs"  # Journal d'actions pour admins
PROFILES_CHANNEL_NAME = "profils-des-groupes"
LEADERBOARD_CHANNEL_NAME = "classements"

EVENEMENT_ROLE_NAME = "Membre de la Meute"
MONTHLY_WINNER_ROLE_NAME = "🏆 Groupe du Mois"


# --- Base de données (JSON) ---
def load_data(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data, file_name):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# Noms des fichiers de données
recommendations_db = "recommendations.json"
events_db = "events.json"
group_scores_db = "group_scores.json"
last_event_db = "last_event.json"


# --- Journal d'actions (Logging) ---
async def log_action(
    guild: discord.Guild, title: str, description: str, color=discord.Color.dark_grey()
):
    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME_ADMIN)
    if log_channel:
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_timestamp(datetime.now())
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass


# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")


# =================================================================================
# === AIDE
# =================================================================================
@bot.group(name="aide", invoke_without_command=True)
async def custom_help(ctx):
    embed = discord.Embed(
        title="🤖 Aide du Bot de la Meute",
        description="Voici la liste des commandes disponibles. Utilisez `!aide <commande>` pour plus de détails.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="🙋‍♂️ Membres & Groupes",
        value="`recommander`, `groupe`, `profil`, `join`, `leave`",
        inline=False,
    )
    embed.add_field(name="🎉 Événements", value="`proposer`, `noter`", inline=False)
    embed.add_field(name="🏆 Compétition", value="`classement`", inline=False)
    await ctx.send(embed=embed)


# =================================================================================
# === COMMANDES UTILISATEURS
# =================================================================================


# --- Commandes de gestion des membres et groupes ---
@bot.command(name="recommander")
@commands.has_role(EVENEMENT_ROLE_NAME)
async def recommend(ctx, new_member: discord.Member):
    data = load_data(recommendations_db)
    server_id = str(ctx.guild.id)
    if server_id not in data:
        data[server_id] = {}
    if str(new_member.id) in data[server_id]:
        await ctx.send("Ce membre est déjà en cours de validation.", ephemeral=True)
        return
    data[server_id][str(new_member.id)] = {
        "recommender_id": ctx.author.id,
        "votes": {str(ctx.author.id)},
        "timestamp": datetime.utcnow().isoformat(),
    }
    save_data(data, recommendations_db)
    assemblee_channel = discord.utils.get(
        ctx.guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
    )
    if not assemblee_channel:
        await ctx.send(
            f"Le salon `{ASSEMBLEE_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )
        return
    embed = discord.Embed(
        title="Nouvelle recommandation de membre",
        description=f"{ctx.author.mention} a recommandé {new_member.mention} pour rejoindre la meute.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"ID du membre: {new_member.id}")
    msg = await assemblee_channel.send(embed=embed)
    await msg.add_reaction("✅")
    await ctx.send(
        f"Votre recommandation pour {new_member.mention} a été soumise au vote dans {assemblee_channel.mention}.",
        ephemeral=True,
    )
    await log_action(
        ctx.guild,
        "Recommandation",
        f"{ctx.author.mention} a recommandé {new_member.mention}.",
        color=discord.Color.blue(),
    )


@bot.command(name="profil")
@commands.has_role(EVENEMENT_ROLE_NAME)
async def group_profile(ctx, *, description: str):
    profile_channel = discord.utils.get(
        ctx.guild.text_channels, name=PROFILES_CHANNEL_NAME
    )
    if not profile_channel:
        await ctx.send(
            f"❌ Le salon `{PROFILES_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )
        return
    author_group_role = discord.utils.find(
        lambda r: r.name.startswith("groupe "), ctx.author.roles
    )
    if not author_group_role:
        await ctx.send(
            "❌ Vous devez faire partie d'un groupe pour utiliser cette commande.",
            ephemeral=True,
        )
        return
    existing_message = None
    async for message in profile_channel.history(limit=100):
        if (
            message.author == bot.user
            and message.embeds
            and message.embeds[0].title
            == f"Profil du groupe : {author_group_role.name[7:]}"
        ):
            existing_message = message
            break
    embed = discord.Embed(
        title=f"Profil du groupe : {author_group_role.name[7:]}",
        description=description,
        color=author_group_role.color,
    )
    members_list = "\n".join(
        [f"• {member.display_name}" for member in author_group_role.members]
    )
    embed.add_field(name="Membres", value=members_list or "Aucun membre", inline=False)
    embed.set_footer(text=f"Profil mis à jour par {ctx.author.display_name}")
    if existing_message:
        await existing_message.edit(embed=embed)
    else:
        await profile_channel.send(embed=embed)
    await ctx.send("✅ Profil de groupe mis à jour !", ephemeral=True, delete_after=10)
    await ctx.message.delete()


# --- Commandes de gestion des événements ---
class ProposeEventModal(Modal, title="Proposer un nouvel événement"):
    category = TextInput(
        label="Catégorie",
        placeholder="Ex: [Jeu], [Chill], [Exploration]...",
        required=True,
    )
    event_title = TextInput(
        label="Titre de l'événement",
        placeholder="Le titre doit être clair et concis.",
        required=True,
    )
    description = TextInput(
        label="Description (optionnel)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        group_role = discord.utils.find(
            lambda r: r.name.startswith("groupe "), interaction.user.roles
        )
        if not group_role:
            await interaction.response.send_message(
                "❌ Vous devez faire partie d'un groupe.", ephemeral=True
            )
            return
        gestion_slug = group_role.name[len("groupe ") :].lower().replace(" ", "-")
        gestion_channel = discord.utils.get(
            interaction.guild.text_channels, name=f"gestion-{gestion_slug}"
        )
        if not gestion_channel:
            await interaction.response.send_message(
                "❌ Salon de gestion introuvable.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title=f"Nouvelle proposition : {self.event_title.value}",
            color=group_role.color,
        )
        embed.set_author(
            name=f"Proposé par {interaction.user.display_name}",
            icon_url=interaction.user.avatar.url,
        )
        embed.add_field(name="Catégorie", value=self.category.value, inline=False)
        if self.description.value:
            embed.add_field(
                name="Description", value=self.description.value, inline=False
            )
        msg = await gestion_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        await interaction.response.send_message(
            f"✅ Proposition envoyée dans {gestion_channel.mention} !", ephemeral=True
        )
        await log_action(
            interaction.guild,
            "Proposition d'événement",
            f"{interaction.user.mention} a proposé `{self.event_title.value}` pour le groupe **{group_role.name}**.",
        )


@bot.tree.command(
    name="proposer", description="Ouvre une fenêtre pour proposer un nouvel événement."
)
@app_commands.checks.has_role(EVENEMENT_ROLE_NAME)
async def proposer_slash(interaction: discord.Interaction):
    """Ouvre une fenêtre pour proposer un nouvel événement."""
    await interaction.response.send_modal(ProposeEventModal())


@bot.command(name="noter")
@commands.has_role(EVENEMENT_ROLE_NAME)
async def rate_event(ctx, event_id: str, rating: int):
    """Note un événement proposé. `!noter <ID de l'événement> <note de 1 à 5>`."""
    if not (1 <= rating <= 5):
        await ctx.send("❌ La note doit être comprise entre 1 et 5.")
        return

    events_data = load_data(events_db)
    server_id = str(ctx.guild.id)

    if server_id not in events_data or event_id not in events_data[server_id]:
        await ctx.send("❌ Cet ID d'événement n'existe pas ou n'est plus valide.")
        return

    # Enregistrer la note
    event = events_data[server_id][event_id]
    event["ratings"][str(ctx.author.id)] = rating

    # Recalculer la moyenne
    total_ratings = sum(event["ratings"].values())
    event["average_rating"] = round(total_ratings / len(event["ratings"]), 2)

    save_data(events_data, events_db)
    await ctx.send(
        f'✅ Votre note de **{rating}/5** a bien été prise en compte pour l\'événement "{event["title"]}". Nouvelle note moyenne : **{event["average_rating"]}**.'
    )


# --- Commande de classement ---
@bot.command(name="classement")
@commands.has_permissions(manage_messages=True)
async def leaderboard_command(ctx):
    await ctx.send("Mise à jour des classements...", ephemeral=True)
    channel = discord.utils.get(ctx.guild.text_channels, name=LEADERBOARD_CHANNEL_NAME)
    if channel:
        await channel.purge(limit=5)
        embed = await generate_leaderboard_embed(ctx.guild)
        await channel.send(embed=embed)


# =================================================================================
# === TÂCHES EN ARRIÈRE-PLAN (TASKS)
# =================================================================================
@tasks.loop(hours=1)
async def check_recommendations():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        data = load_data(recommendations_db)
        server_id = str(guild.id)
        if server_id not in data:
            continue
        member_role = discord.utils.get(guild.roles, name=EVENEMENT_ROLE_NAME)
        if not member_role:
            continue
        total_members = len(member_role.members)
        majority_needed = (total_members // 2) + 1
        assemblee_channel = discord.utils.get(
            guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
        )
        for member_id_str, info in list(data[server_id].items()):
            try:
                async for message in assemblee_channel.history(limit=100):
                    if (
                        message.embeds
                        and str(member_id_str) in message.embeds[0].footer.text
                    ):
                        reaction = discord.utils.get(message.reactions, emoji="✅")
                        if reaction:
                            voters = {
                                user.id
                                async for user in reaction.users()
                                if not user.bot and member_role in user.roles
                            }
                            if len(voters) >= majority_needed:
                                new_member = guild.get_member(int(member_id_str))
                                recommender = guild.get_member(info["recommender_id"])
                                if new_member and recommender:
                                    await new_member.add_roles(member_role)
                                    await assemblee_channel.send(
                                        f"🎉 La recommandation pour {new_member.mention} a été validée !"
                                    )
                                    await log_action(
                                        guild,
                                        "Membre Validé",
                                        f"{new_member.mention} a été validé sur recommandation de {recommender.mention}.",
                                        color=discord.Color.green(),
                                    )
                                    await message.delete()
                                    del data[server_id][member_id_str]
            except Exception as e:
                print(f"Erreur check_recommendations: {e}")
        save_data(data, recommendations_db)


@tasks.loop(hours=1)
async def update_recommenders_list():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=RECOMMENDERS_CHANNEL_NAME)
        role = discord.utils.get(guild.roles, name=EVENEMENT_ROLE_NAME)
        if not channel or not role:
            continue
        await channel.purge(limit=10)
        members_with_role = role.members
        embed = discord.Embed(
            title="Membres pouvant vous recommander",
            description="Voici la liste des membres qui peuvent utiliser `!recommander`.",
            color=discord.Color.green(),
        )
        member_list_str = "\n".join(
            [f"• {member.mention}" for member in members_with_role]
        )
        embed.description += f"\n\n{member_list_str}"
        await channel.send(embed=embed)


@tasks.loop(hours=1)
async def check_group_votes():
    """Vérifie les votes de proposition au sein des groupes."""
    await bot.wait_until_ready()
    for guild in bot.guilds:
        proposals_channel = discord.utils.get(
            guild.text_channels, name=EVENT_PROPOSALS_CHANNEL_NAME
        )
        if not proposals_channel:
            continue

        for channel in guild.text_channels:
            if channel.name.startswith("gestion-"):
                group_name = channel.name.replace("gestion-", "groupe ")
                group_role = discord.utils.get(guild.roles, name=group_name)
                if not group_role or not group_role.members:
                    continue

                member_count = len(group_role.members)
                majority_approve = (member_count // 2) + 1
                majority_reject = (member_count // 2) + 1

                try:
                    async for message in channel.history(limit=50):
                        if not message.embeds or message.author != bot.user:
                            continue

                        yes_reac = discord.utils.get(message.reactions, emoji="✅")
                        no_reac = discord.utils.get(message.reactions, emoji="❌")

                        if not yes_reac and not no_reac:
                            continue

                        voters_yes = {
                            user.id
                            async for user in yes_reac.users()
                            if group_role in user.roles
                        }
                        voters_no = {
                            user.id
                            async for user in no_reac.users()
                            if group_role in user.roles
                        }

                        if len(voters_yes) >= majority_approve:
                            # Proposition acceptée
                            event_title = message.embeds[0].description.strip("*")
                            categorie_field = discord.utils.get(
                                message.embeds[0].fields, name="Catégorie"
                            )
                            event_categorie = (
                                categorie_field.value if categorie_field else "[Autre]"
                            )

                            # Ajout à la base de données des événements
                            events_data = load_data(events_db)
                            server_id = str(guild.id)
                            if server_id not in events_data:
                                events_data[server_id] = {}
                            event_id = str(message.id)
                            events_data[server_id][event_id] = {
                                "title": event_title,
                                "category": event_categorie,  # <-- ON SAUVEGARDE LA CATÉGORIE
                                "proposer_group": group_role.name,
                                "ratings": {},
                                "average_rating": 0,
                            }
                            save_data(events_data, events_db)

                            # Annonce dans le salon des propositions
                            embed = discord.Embed(
                                title="Nouvel événement disponible aux votes",
                                description=f"**{event_title}**",
                                color=discord.Color.green(),
                            )
                            embed.set_footer(text=f"ID de l'événement : {event_id}")
                            await proposals_channel.send(
                                f"Le groupe *{group_role.name}* a validé une nouvelle proposition ! Utilisez `!noter {event_id} <note de 1 à 5>` pour donner votre avis.",
                                embed=embed,
                            )
                            await message.delete()

                        elif len(voters_no) >= majority_reject:
                            # Proposition rejetée
                            await channel.send(
                                f'La proposition "{message.embeds[0].description}" a été rejetée par le groupe.',
                                delete_after=30,
                            )
                            await message.delete()
                except Exception as e:
                    print(f"Erreur vérification vote groupe {channel.name}: {e}")


@tasks.loop(hours=24)
async def weekly_vote_announcement():
    """Annonce le début du vote pour l'événement de la semaine."""
    # Déclenché le Mercredi à 18h
    if datetime.now().weekday() == 2 and datetime.now().hour == 18:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            events_data = load_data(events_db).get(str(guild.id), {})
            last_event_data = load_data(last_event_db).get(str(guild.id), {})

            # Filtrer l'événement de la semaine précédente
            eligible_events = {
                k: v for k, v in events_data.items() if k != last_event_data.get("id")
            }

            if not eligible_events:
                await assemblee_channel.send(
                    "Il n'y a aucun nouvel événement à voter pour cette semaine."
                )
                return

            # Trier par note moyenne
            sorted_events = sorted(
                eligible_events.items(),
                key=lambda item: item[1]["average_rating"],
                reverse=True,
            )

            options = [
                discord.SelectOption(
                    # --- AJOUT : On affiche la catégorie dans le label ---
                    label=f"{event.get('category', '[Autre]')} {event['title']}"[:100],
                    description=f"Note: {event['average_rating']}/5",
                    value=event_id,
                )
                for event_id, event in sorted_events
            ]

            if not options:
                await assemblee_channel.send(
                    "Aucun événement éligible pour le vote cette semaine."
                )
                return

            class WeeklyVoteSelect(Select):
                def __init__(self):
                    super().__init__(
                        placeholder="Choisissez l'événement de la semaine",
                        options=options,
                    )

                async def callback(self, interaction: discord.Interaction):
                    # Cette partie pourrait être étendue pour enregistrer les votes si nécessaire
                    await interaction.response.send_message(
                        f"Votre vote pour l'événement avec l'ID `{self.values[0]}` a été enregistré !",
                        ephemeral=True,
                    )

            view = View()
            view.add_item(WeeklyVoteSelect())
            await assemblee_channel.send(
                "🗳️ **Vote de la semaine !**\nChoisissez l'événement de la semaine prochaine parmi les propositions (triées par popularité) :",
                view=view,
            )


@tasks.loop(hours=24)
async def announce_winner():
    """Annonce l'événement gagnant de la semaine."""
    # Déclenché le Vendredi à 20h
    if datetime.now().weekday() == 4 and datetime.now().hour == 20:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            # Simuler la récupération du gagnant (idéalement, il faudrait un vrai système de comptage des votes du Select Menu)
            # Pour cet exemple, on prend le plus populaire qui n'était pas le dernier événement.
            events_data = load_data(events_db).get(str(guild.id), {})
            last_event_data = load_data(last_event_db).get(str(guild.id), {})

            eligible_events = {
                k: v for k, v in events_data.items() if k != last_event_data.get("id")
            }
            if not eligible_events:
                await assemblee_channel.send(
                    "Aucun événement n'a été sélectionné cette semaine."
                )
                return

            winner_id, winner_info = max(
                eligible_events.items(), key=lambda item: item[1]["average_rating"]
            )

            # Annonce et mise à jour
            winner_category = winner_info.get("category", "[Autre]")
            announcement_text = f"🎉 L'événement de la semaine est : **{winner_category} {winner_info['title']}** ! Proposé par le groupe *{winner_info['proposer_group']}*."
            announcement_message = await assemblee_channel.send(announcement_text)

            # --- AJOUT : Création d'un fil de discussion pour le feedback ---
            try:
                thread_name = f"Feedback sur - {winner_info['title']}"[:100]
                # Durée d'archivage automatique de 3 jours (4320 minutes)
                feedback_thread = await announcement_message.create_thread(
                    name=thread_name, auto_archive_duration=4320
                )
                await feedback_thread.send(
                    "Partagez ici vos retours, avis et meilleures captures d'écran de l'événement ! 📸"
                )
            except discord.Forbidden:
                await assemblee_channel.send(
                    "*(Je n'ai pas la permission de créer un fil de discussion pour le feedback.)*"
                )
            except Exception as e:
                print(f"Erreur lors de la création du fil de discussion : {e}")
            # Sauvegarder comme dernier événement
            save_data(
                {"id": winner_id, "title": winner_info["title"]},
                f"{guild.id}_{last_event_db}",
            )

            # Mettre à jour le score du groupe
            group_scores = load_data(group_scores_db)
            server_id = str(guild.id)
            if server_id not in group_scores:
                group_scores[server_id] = {}
            group_name = winner_info["proposer_group"]
            group_scores[server_id][group_name] = (
                group_scores[server_id].get(group_name, 0) + 1
            )
            save_data(group_scores, group_scores_db)

            # Supprimer l'événement de la liste des propositions actives
            events_data[winner_id]["status"] = "past"
            save_data(events_data, events_db)


@tasks.loop(hours=24)
async def monthly_intercommunity_event():
    """Organise l'événement mensuel."""
    # Déclenché le premier jour du mois à 12h
    if datetime.now().day == 1 and datetime.now().hour == 12:
        for guild in bot.guilds:
            group_scores = load_data(group_scores_db).get(str(guild.id), {})
            if not group_scores:
                continue

            winning_group = max(group_scores, key=group_scores.get)
            score = group_scores[winning_group]

            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if assemblee_channel:
                embed = discord.Embed(
                    title="🏆 Soirée Inter-Communautaire du Mois ! 🏆",
                    description=f"Ce mois-ci, le groupe **{winning_group}** est à l'honneur avec un score de **{score}** événements validés !\n\nIls organiseront la soirée spéciale. Préparez-vous !",
                    color=discord.Color.gold(),
                )
                await assemblee_channel.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_roles=True)
async def groupe(ctx, nom: str, couleur: discord.Colour):
    member = ctx.author
    guild = ctx.guild

    if any(role.name.startswith("groupe ") for role in member.roles):
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


@tasks.loop(hours=6)
async def update_leaderboard():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=LEADERBOARD_CHANNEL_NAME)
        if channel:
            await channel.purge(limit=5)
            embed = await generate_leaderboard_embed(guild)
            await channel.send(embed=embed)


async def generate_leaderboard_embed(guild: discord.Guild):
    embed = discord.Embed(
        title="🏆 Classements de la Meute 🏆", color=discord.Color.gold()
    )
    group_scores = load_data(group_scores_db).get(str(guild.id), {})
    sorted_groups = sorted(group_scores.items(), key=lambda item: item[1], reverse=True)
    group_text = "\n".join(
        [
            f"**{i + 1}.** {name} ({score} pts)"
            for i, (name, score) in enumerate(sorted_groups[:5])
        ]
    )
    embed.add_field(
        name="Top Groupes du Mois",
        value=group_text or "Aucun score ce mois-ci.",
        inline=False,
    )
    events_data = load_data(events_db).get(str(guild.id), {})
    all_raters = [
        user_id
        for event in events_data.values()
        for user_id in event.get("ratings", {}).keys()
    ]
    top_raters = Counter(all_raters).most_common(5)
    raters_text = "\n".join(
        [
            f"**{i + 1}.** <@{user_id}> ({count} notes)"
            for i, (user_id, count) in enumerate(top_raters)
        ]
    )
    embed.add_field(
        name="Membres les Plus Actifs",
        value=raters_text or "Personne n'a encore noté d'événement.",
        inline=False,
    )
    all_events = sorted(
        [e for e in events_data.values() if e.get("average_rating", 0) > 0],
        key=lambda e: e["average_rating"],
        reverse=True,
    )
    events_text = "\n".join(
        [f"**{e['average_rating']}/5** - {e['title']}" for e in all_events[:5]]
    )
    embed.add_field(
        name="Meilleurs Événements Proposés",
        value=events_text or "Aucun événement noté.",
        inline=False,
    )
    embed.set_footer(
        text=f"Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    return embed


# =================================================================================
# === ÉVÉNEMENTS DU BOT
# =================================================================================
@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s)")
    except Exception as e:
        print(f"Erreur de synchronisation : {e}")
    print("Démarrage des tâches en arrière-plan...")
    check_recommendations.start()
    update_recommenders_list.start()
    check_group_votes.start()
    weekly_vote_announcement.start()
    announce_winner.start()
    monthly_intercommunity_event.start()
    update_leaderboard.start()


@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        embed = discord.Embed(
            title=f"Bienvenue, {member.display_name} !",
            description="Notre communauté fonctionne sur un système de **cooptation**...",
            color=discord.Color.blue(),
        )
        await channel.send(content=member.mention, embed=embed)


# --- Démarrage du Bot ---
if __name__ == "__main__":
    if TOKEN is None:
        print(
            "Erreur : Le token Discord n'est pas défini. Veuillez créer un fichier .env avec DISCORD_TOKEN=votretokendeconnexion"
        )
    else:
        bot.run(TOKEN)
