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
# Ces noms doivent correspondre exactement à ceux de votre serveur Discord.
ASSEMBLEE_CHANNEL_NAME = "assemblée"
EVENT_PROPOSALS_CHANNEL_NAME = "propositions-evenements"
WELCOME_CHANNEL_NAME = "bienvenue-lis-moi"
RECOMMENDERS_CHANNEL_NAME = "qui-peut-me-recommander"
LOG_CHANNEL_NAME_ADMIN = "bot-logs"
PROFILES_CHANNEL_NAME = "profils-des-groupes"
LEADERBOARD_CHANNEL_NAME = "classements"
REGISTRE_CHANNEL_NAME = "registre-de-la-meute"

EVENEMENT_ROLE_NAME = "Membre de la Meute"
MONTHLY_WINNER_ROLE_NAME = "🏆 Groupe du Mois"
MAX_GROUP_MEMBERS = 10  # Nombre maximum de membres par groupe


# --- Gestion de la base de données (JSON) ---
def load_data(file_name):
    """Charge les données depuis un fichier JSON."""
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data, file_name):
    """Sauvegarde les données dans un fichier JSON."""
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# Noms des fichiers de données
recommendations_db = "recommendations.json"
events_db = "events.json"
group_scores_db = "group_scores.json"
weekly_votes_db = "weekly_votes.json"


# --- Journal d'actions (Logging) ---
async def log_action(
    guild: discord.Guild, title: str, description: str, color=discord.Color.dark_grey()
):
    """Envoie un message de log dans le salon dédié aux admins."""
    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME_ADMIN)
    if log_channel:
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_timestamp(datetime.now())
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            print(
                f"Erreur: Impossible d'envoyer un log dans le salon '{LOG_CHANNEL_NAME_ADMIN}'. Permissions manquantes."
            )


# --- Configuration du Bot ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("§"), intents=intents)


# =================================================================================
# === COMMANDES SLASH (/)
# =================================================================================


# --- Commande d'aide ---
@bot.tree.command(
    name="aide", description="Affiche la liste des commandes et leur utilité."
)
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Aide du Bot de la Meute",
        description="Voici la liste des commandes slash (/) disponibles pour interagir avec la meute.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="🐺 Gestion des Groupes",
        value="`/groupe` : Crée un nouveau groupe (admin).\n"
        "`/groupes` : Affiche la liste des groupes à rejoindre.\n"
        "`/join` : Rejoint un groupe existant.\n"
        "`/leave` : Quitte votre groupe actuel.\n"
        "`/profil` : Met à jour la description de votre groupe.",
        inline=False,
    )
    embed.add_field(
        name="🙋‍♂️ Gouvernance",
        value="`/recommander` : Propose un nouveau membre à la cooptation.\n"
        "`/noter` : Donne une note de 1 à 5 à une proposition d'événement.",
        inline=False,
    )
    embed.add_field(
        name="🎉 Événements & Compétition",
        value="`/proposer` : Ouvre un formulaire pour proposer un nouvel événement.\n"
        "`/classement` : Affiche les classements actuels.",
        inline=False,
    )
    embed.set_footer(text="Toutes les commandes commencent par un /")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Commandes de gestion des membres et groupes ---
@bot.tree.command(
    name="groupe",
    description="Crée un nouveau groupe avec rôle et salons dédiés (Admin).",
)
@app_commands.describe(
    nom="Le nom du nouveau groupe.",
    couleur="Le code hexadécimal de la couleur (ex: #FF5733).",
)
@app_commands.checks.has_permissions(manage_roles=True)
async def groupe(interaction: discord.Interaction, nom: str, couleur: str):
    await interaction.response.defer(ephemeral=True)

    try:
        couleur_obj = discord.Colour.from_str(couleur)
    except ValueError:
        await interaction.followup.send(
            "❌ Le format de la couleur est invalide. Utilisez un code hexadécimal comme `#FF5733`.",
            ephemeral=True,
        )
        return

    guild = interaction.guild
    role_name = f"groupe {nom}"

    if discord.utils.get(guild.roles, name=role_name):
        await interaction.followup.send(
            f"❌ Un groupe nommé '{nom}' existe déjà.", ephemeral=True
        )
        return

    nouveau_role = await guild.create_role(
        name=role_name,
        colour=couleur_obj,
        reason=f"Création du groupe par {interaction.user}",
    )

    # Mise à jour de la création des salons pour correspondre à la nouvelle structure
    categorie = await guild.create_category(f"🐺 GROUPE {nom.upper()}")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        nouveau_role: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, connect=True, speak=True
        ),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    nom_slug = nom.lower().replace(" ", "-")
    await categorie.create_text_channel(f"💬-{nom_slug}", overwrites=overwrites)
    await categorie.create_text_channel(f"🔒-gestion-{nom_slug}", overwrites=overwrites)
    await categorie.create_voice_channel(f"🔊 Vocal - {nom}", overwrites=overwrites)

    await interaction.followup.send(
        f"✅ Le groupe '{nom}' a été créé avec succès !", ephemeral=True
    )
    await log_action(
        guild,
        "Création de Groupe",
        f"Le groupe **{nom}** a été créé par {interaction.user.mention}.",
        color=discord.Color.green(),
    )


@bot.tree.command(
    name="groupes",
    description="Affiche la liste de tous les groupes qu'il est possible de rejoindre.",
)
async def groupes(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    all_group_roles = [role for role in guild.roles if role.name.startswith("groupe ")]

    embed = discord.Embed(
        title="🐺 Liste des Groupes de la Meute",
        description="Voici les groupes que tu peux rejoindre. Utilise `/join <nom du groupe>`.",
        color=discord.Color.purple(),
    )

    if not all_group_roles:
        embed.description = "Il n'y a aucun groupe à rejoindre pour le moment."
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    joinable_groups_text = ""
    for role in sorted(all_group_roles, key=lambda r: r.name):
        member_count = len(role.members)
        if member_count < MAX_GROUP_MEMBERS:
            places_left = MAX_GROUP_MEMBERS - member_count
            joinable_groups_text += f"**{role.name[7:]}** - `{member_count}/{MAX_GROUP_MEMBERS}` membres ({places_left} places restantes)\n"

    if not joinable_groups_text:
        embed.add_field(
            name="Groupes disponibles",
            value="Aucun groupe n'a de place libre pour le moment.",
            inline=False,
        )
    else:
        embed.add_field(
            name="Groupes disponibles", value=joinable_groups_text, inline=False
        )

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="join", description="Rejoins un groupe existant s'il n'est pas complet."
)
@app_commands.describe(nom_groupe="Le nom exact du groupe que tu veux rejoindre.")
async def join(interaction: discord.Interaction, nom_groupe: str):
    member = interaction.user
    guild = interaction.guild
    role_demande = discord.utils.get(guild.roles, name=f"groupe {nom_groupe}")

    if not role_demande:
        await interaction.response.send_message(
            f"❌ Le groupe '{nom_groupe}' n'existe pas.", ephemeral=True
        )
        return

    if len(role_demande.members) >= MAX_GROUP_MEMBERS:
        await interaction.response.send_message(
            f"❌ Ce groupe est déjà complet ({MAX_GROUP_MEMBERS} membres).",
            ephemeral=True,
        )
        return

    ancien_role = discord.utils.find(
        lambda r: r.name.startswith("groupe "), member.roles
    )
    if ancien_role:
        await member.remove_roles(ancien_role, reason="Changement de groupe")

    await member.add_roles(role_demande, reason=f"A rejoint le groupe {nom_groupe}")
    await interaction.response.send_message(
        f"✅ Tu as bien rejoint le groupe **{nom_groupe}** !", ephemeral=True
    )


@bot.tree.command(name="leave", description="Quitte votre groupe actuel.")
async def leave(interaction: discord.Interaction):
    member = interaction.user
    guild = interaction.guild
    role_groupe = discord.utils.find(
        lambda r: r.name.startswith("groupe "), member.roles
    )

    if not role_groupe:
        await interaction.response.send_message(
            "❌ Tu ne fais partie d'aucun groupe.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    nom_groupe_original = role_groupe.name[7:]
    await member.remove_roles(role_groupe, reason="A quitté le groupe")
    await interaction.followup.send(
        f"✅ Tu as quitté le groupe **{nom_groupe_original}**.", ephemeral=True
    )

    # Re-fetch the role to get an updated member count
    role_groupe_updated = guild.get_role(role_groupe.id)
    if role_groupe_updated and len(role_groupe_updated.members) == 0:
        await log_action(
            guild,
            "Nettoyage de Groupe",
            f"Le groupe **{nom_groupe_original}** est vide et va être supprimé.",
            color=discord.Color.orange(),
        )

        # Mise à jour de la recherche de la catégorie
        categorie = discord.utils.get(
            guild.categories, name=f"🐺 GROUPE {nom_groupe_original.upper()}"
        )
        if categorie:
            for channel in categorie.channels:
                try:
                    await channel.delete(reason="Groupe vide")
                except discord.HTTPException as e:
                    print(f"Erreur lors de la suppression du salon {channel.name}: {e}")
            try:
                await categorie.delete(reason="Groupe vide")
            except discord.HTTPException as e:
                print(
                    f"Erreur lors de la suppression de la catégorie {categorie.name}: {e}"
                )

        try:
            await role_groupe_updated.delete(reason="Groupe vide")
            await log_action(
                guild,
                "Groupe Supprimé",
                f"Le groupe **{nom_groupe_original}** a été supprimé avec succès.",
                color=discord.Color.red(),
            )
        except discord.HTTPException as e:
            print(
                f"Erreur lors de la suppression du rôle {role_groupe_updated.name}: {e}"
            )


@bot.tree.command(
    name="recommander",
    description="Lance un vote pour faire entrer un nouveau membre dans la meute.",
)
@app_commands.describe(membre="Le membre que tu souhaites recommander.")
@app_commands.checks.has_role(EVENEMENT_ROLE_NAME)
async def recommander(interaction: discord.Interaction, membre: discord.Member):
    data = load_data(recommendations_db)
    server_id = str(interaction.guild.id)
    if server_id not in data:
        data[server_id] = {}

    if str(membre.id) in data[server_id]:
        await interaction.response.send_message(
            "Ce membre est déjà en cours de validation.", ephemeral=True
        )
        return

    data[server_id][str(membre.id)] = {
        "recommender_id": interaction.user.id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    save_data(data, recommendations_db)

    assemblee_channel = discord.utils.get(
        interaction.guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
    )
    if not assemblee_channel:
        await interaction.response.send_message(
            f"Le salon `{ASSEMBLEE_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Nouvelle recommandation de membre",
        description=f"{interaction.user.mention} a recommandé {membre.mention} pour rejoindre la meute.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"ID du membre: {membre.id}")
    msg = await assemblee_channel.send(embed=embed)
    await msg.add_reaction("✅")

    await interaction.response.send_message(
        f"Votre recommandation pour {membre.mention} a été soumise au vote dans {assemblee_channel.mention}.",
        ephemeral=True,
    )
    await log_action(
        interaction.guild,
        "Recommandation",
        f"{interaction.user.mention} a recommandé {membre.mention}.",
        color=discord.Color.blue(),
    )


class GroupProfileModal(Modal, title="Mise à jour du profil de groupe"):
    description = TextInput(
        label="Description de votre groupe",
        style=discord.TextStyle.paragraph,
        placeholder="Décrivez ici la philosophie de votre groupe, vos jeux préférés, etc.",
        required=True,
        max_length=1024,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        profile_channel = discord.utils.get(
            interaction.guild.text_channels, name=PROFILES_CHANNEL_NAME
        )
        if not profile_channel:
            await interaction.followup.send(
                f"❌ Le salon `{PROFILES_CHANNEL_NAME}` est introuvable.",
                ephemeral=True,
            )
            return

        author_group_role = discord.utils.find(
            lambda r: r.name.startswith("groupe "), interaction.user.roles
        )
        if not author_group_role:
            await interaction.followup.send(
                "❌ Vous devez faire partie d'un groupe pour utiliser cette commande.",
                ephemeral=True,
            )
            return

        existing_message = None
        async for message in profile_channel.history(limit=100):
            if (
                message.author == bot.user
                and message.embeds
                and message.embeds[0].footer.text
                == f"ID du groupe : {author_group_role.id}"
            ):
                existing_message = message
                break

        embed = discord.Embed(
            title=f"Profil du groupe : {author_group_role.name[7:]}",
            description=self.description.value,
            color=author_group_role.color,
        )
        members_list = "\n".join(
            [f"• {member.display_name}" for member in author_group_role.members]
        )
        embed.add_field(
            name="Membres", value=members_list or "Aucun membre", inline=False
        )
        embed.set_footer(text=f"ID du groupe : {author_group_role.id}")

        if existing_message:
            await existing_message.edit(embed=embed)
        else:
            await profile_channel.send(embed=embed)

        await interaction.followup.send(
            "✅ Profil de groupe mis à jour !", ephemeral=True
        )


@bot.tree.command(
    name="profil",
    description="Définit ou met à jour le message de présentation de votre groupe.",
)
@app_commands.checks.has_role(EVENEMENT_ROLE_NAME)
async def profil(interaction: discord.Interaction):
    await interaction.response.send_modal(GroupProfileModal())


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
        label="Description",
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

        gestion_slug = group_role.name[7:].lower().replace(" ", "-")
        gestion_channel = discord.utils.get(
            interaction.guild.text_channels, name=f"🔒-gestion-{gestion_slug}"
        )
        if not gestion_channel:
            await interaction.response.send_message(
                "❌ Salon de gestion introuvable pour votre groupe.", ephemeral=True
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
async def proposer(interaction: discord.Interaction):
    await interaction.response.send_modal(ProposeEventModal())


@bot.tree.command(name="noter", description="Note un événement proposé de 1 à 5.")
@app_commands.describe(
    id_evenement="L'ID du message de l'événement à noter.", note="Votre note de 1 à 5."
)
@app_commands.choices(
    note=[
        app_commands.Choice(name="⭐ (1/5)", value=1),
        app_commands.Choice(name="⭐⭐ (2/5)", value=2),
        app_commands.Choice(name="⭐⭐⭐ (3/5)", value=3),
        app_commands.Choice(name="⭐⭐⭐⭐ (4/5)", value=4),
        app_commands.Choice(name="⭐⭐⭐⭐⭐ (5/5)", value=5),
    ]
)
@app_commands.checks.has_role(EVENEMENT_ROLE_NAME)
async def noter(
    interaction: discord.Interaction, id_evenement: str, note: app_commands.Choice[int]
):
    events_data = load_data(events_db)
    server_id = str(interaction.guild.id)

    if server_id not in events_data or id_evenement not in events_data[server_id]:
        await interaction.response.send_message(
            "❌ Cet ID d'événement n'existe pas ou n'est plus valide.", ephemeral=True
        )
        return

    event = events_data[server_id][id_evenement]
    event["ratings"][str(interaction.user.id)] = note.value
    total_ratings = sum(event["ratings"].values())
    event["average_rating"] = round(total_ratings / len(event["ratings"]), 2)
    save_data(events_data, events_db)

    await interaction.response.send_message(
        f'✅ Votre note de **{note.value}/5** a bien été prise en compte pour l\'événement "{event["title"]}".',
        ephemeral=True,
    )


@bot.tree.command(
    name="classement",
    description="Force la mise à jour et l'affichage des classements.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def classement(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = discord.utils.get(
        interaction.guild.text_channels, name=LEADERBOARD_CHANNEL_NAME
    )
    if channel:
        await channel.purge(limit=5)
        embed = await generate_leaderboard_embed(interaction.guild)
        await channel.send(embed=embed)
        await interaction.followup.send("✅ Classements mis à jour.", ephemeral=True)
    else:
        await interaction.followup.send(
            f"❌ Le salon `{LEADERBOARD_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )


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
        registre_channel = discord.utils.get(
            guild.text_channels, name=REGISTRE_CHANNEL_NAME
        )

        for member_id_str, info in list(data[server_id].items()):
            try:
                async for message in assemblee_channel.history(limit=100):
                    if (
                        message.embeds
                        and str(member_id_str) in message.embeds[0].footer.text
                    ):
                        reaction = discord.utils.get(message.reactions, emoji="✅")
                        if reaction and reaction.count >= majority_needed:
                            new_member = guild.get_member(int(member_id_str))
                            recommender = guild.get_member(info["recommender_id"])
                            if new_member and recommender:
                                await new_member.add_roles(member_role)
                                await assemblee_channel.send(
                                    f"🎉 La recommandation pour {new_member.mention} a été validée !"
                                )

                                if registre_channel:
                                    await registre_channel.send(
                                        f"🐺 Bienvenue à {new_member.mention}, qui a rejoint la meute sur recommandation de {recommender.mention}."
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
                print(f"Erreur dans check_recommendations: {e}")
        save_data(data, recommendations_db)


@tasks.loop(hours=1)
async def check_group_votes():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        proposals_channel = discord.utils.get(
            guild.text_channels, name=EVENT_PROPOSALS_CHANNEL_NAME
        )
        if not proposals_channel:
            continue

        for channel in guild.text_channels:
            if channel.name.startswith("🔒-gestion-"):
                group_name_slug = channel.name[len("🔒-gestion-") :]
                group_role = discord.utils.find(
                    lambda r: r.name[7:].lower().replace(" ", "-") == group_name_slug,
                    guild.roles,
                )
                if not group_role or not group_role.members:
                    continue

                member_count = len(group_role.members)
                majority_approve = (member_count // 2) + 1

                try:
                    async for message in channel.history(limit=50):
                        if not message.embeds or message.author != bot.user:
                            continue

                        yes_reac = discord.utils.get(message.reactions, emoji="✅")
                        no_reac = discord.utils.get(message.reactions, emoji="❌")

                        if not yes_reac:
                            continue

                        if yes_reac.count >= majority_approve:
                            event_title = message.embeds[0].title[
                                len("Nouvelle proposition : ") :
                            ]
                            category_field = discord.utils.get(
                                message.embeds[0].fields, name="Catégorie"
                            )
                            event_category = (
                                category_field.value if category_field else "[Autre]"
                            )

                            events_data = load_data(events_db)
                            server_id = str(guild.id)
                            if server_id not in events_data:
                                events_data[server_id] = {}

                            event_id = str(message.id)
                            events_data[server_id][event_id] = {
                                "title": event_title,
                                "category": event_category,
                                "proposer_group": group_role.name,
                                "ratings": {},
                                "average_rating": 0,
                                "status": "active",
                            }
                            save_data(events_data, events_db)

                            embed = discord.Embed(
                                title=f"Nouvel événement : {event_category} {event_title}",
                                description=f"Proposé par le groupe **{group_role.name[7:]}**.",
                                color=discord.Color.green(),
                            )
                            embed.set_footer(text=f"ID de l'événement : {event_id}")
                            await proposals_channel.send(
                                f"Une nouvelle proposition a été validée ! Utilisez `/noter id_evenement:{event_id}` pour donner votre avis.",
                                embed=embed,
                            )
                            await message.delete()

                        elif no_reac and no_reac.count >= majority_approve:
                            await channel.send(
                                f'La proposition "{message.embeds[0].title}" a été rejetée par le groupe.',
                                delete_after=60,
                            )
                            await message.delete()
                except Exception as e:
                    print(f"Erreur dans check_group_votes pour {channel.name}: {e}")


class WeeklyVoteView(View):
    def __init__(self, options, vote_id):
        super().__init__(timeout=172800)
        self.vote_id = vote_id
        self.add_item(self.create_select(options))

    def create_select(self, options):
        select = Select(
            placeholder="Choisissez l'événement de la semaine",
            options=options,
            custom_id=f"weekly_vote_select_{self.vote_id}",
        )
        select.callback = self.select_callback
        return select

    async def select_callback(self, interaction: discord.Interaction):
        votes_data = load_data(weekly_votes_db)
        if self.vote_id not in votes_data:
            votes_data[self.vote_id] = {}

        votes_data[self.vote_id][str(interaction.user.id)] = self.children[0].values[0]
        save_data(votes_data, weekly_votes_db)

        await interaction.response.send_message(
            "✅ Votre vote a bien été pris en compte !", ephemeral=True
        )


@tasks.loop(hours=24)
async def weekly_vote_announcement():
    now = datetime.now()
    if now.weekday() == 2 and now.hour == 18:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            events_data = load_data(events_db).get(str(guild.id), {})
            eligible_events = {
                k: v for k, v in events_data.items() if v.get("status") == "active"
            }
            if not eligible_events:
                await assemblee_channel.send(
                    "Il n'y a aucun nouvel événement à voter pour cette semaine."
                )
                return

            sorted_events = sorted(
                eligible_events.items(),
                key=lambda item: item[1]["average_rating"],
                reverse=True,
            )
            options = [
                discord.SelectOption(
                    label=f"{event.get('category', '[Autre]')} {event['title']}"[:100],
                    description=f"Note: {event['average_rating']}/5",
                    value=event_id,
                )
                for event_id, event in sorted_events[:25]
            ]

            if not options:
                await assemblee_channel.send(
                    "Aucun événement éligible pour le vote cette semaine."
                )
                return

            temp_msg = await assemblee_channel.send("Préparation du vote...")
            vote_id = str(temp_msg.id)

            view = WeeklyVoteView(options, vote_id)
            await temp_msg.edit(
                content="🗳️ **Vote de la semaine !**\nChoisissez l'événement de la semaine prochaine parmi les propositions :",
                view=view,
            )


@tasks.loop(hours=24)
async def announce_winner():
    now = datetime.now()
    if now.weekday() == 4 and now.hour == 20:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            votes_data = load_data(weekly_votes_db)
            if not votes_data:
                # Silently return if no votes are active, to avoid spamming the channel
                return

            latest_vote_id = sorted(votes_data.keys())[-1]
            latest_votes = votes_data[latest_vote_id]

            if not latest_votes:
                await assemblee_channel.send("Personne n'a voté cette semaine !")
                return

            vote_counts = Counter(latest_votes.values())
            winner_id, _ = vote_counts.most_common(1)[0]

            events_data = load_data(events_db)
            server_id = str(guild.id)
            winner_info = events_data.get(server_id, {}).get(winner_id)

            if not winner_info:
                print(
                    f"Erreur: L'ID de l'événement gagnant {winner_id} est introuvable."
                )
                continue

            winner_category = winner_info.get("category", "[Autre]")
            announcement_text = f"🎉 L'événement de la semaine est : **{winner_category} {winner_info['title']}** ! Proposé par le groupe *{winner_info['proposer_group'][7:]}*."
            announcement_message = await assemblee_channel.send(announcement_text)

            try:
                thread_name = f"Feedback sur - {winner_info['title']}"[:100]
                await announcement_message.create_thread(
                    name=thread_name, auto_archive_duration=4320
                )
            except Exception as e:
                print(f"Erreur lors de la création du fil de discussion : {e}")

            group_scores = load_data(group_scores_db)
            if server_id not in group_scores:
                group_scores[server_id] = {}
            group_name = winner_info["proposer_group"]
            group_scores[server_id][group_name] = (
                group_scores[server_id].get(group_name, 0) + 1
            )
            save_data(group_scores, group_scores_db)

            events_data[server_id][winner_id]["status"] = "past"
            save_data(events_data, events_db)

            del votes_data[latest_vote_id]
            save_data(votes_data, weekly_votes_db)


@tasks.loop(hours=24)
async def monthly_intercommunity_event():
    now = datetime.now()
    if now.day == 1 and now.hour == 12:
        for guild in bot.guilds:
            group_scores = load_data(group_scores_db).get(str(guild.id), {})
            if not group_scores:
                continue

            winner_role = discord.utils.get(guild.roles, name=MONTHLY_WINNER_ROLE_NAME)
            if winner_role:
                for member in winner_role.members:
                    await member.remove_roles(winner_role, reason="Fin du mois")

            winning_group_name = max(group_scores, key=group_scores.get)
            score = group_scores[winning_group_name]
            winning_group_role = discord.utils.get(guild.roles, name=winning_group_name)

            assemblee_channel = discord.utils.get(
                guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
            )
            if assemblee_channel:
                embed = discord.Embed(
                    title="🏆 Soirée Inter-Communautaire du Mois ! 🏆",
                    description=f"Ce mois-ci, le groupe **{winning_group_name[7:]}** est à l'honneur avec un score de **{score}** événements validés !\n\nIls organiseront la soirée spéciale et reçoivent le rôle honorifique.",
                    color=discord.Color.gold(),
                )
                await assemblee_channel.send(embed=embed)

            if winning_group_role and winner_role:
                for member in winning_group_role.members:
                    await member.add_roles(winner_role, reason="Gagnant du mois")

            group_scores[str(guild.id)] = {}
            save_data(group_scores, group_scores_db)


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
            f"**{i + 1}.** {name[7:]} ({score} pts)"
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
    check_group_votes.start()
    weekly_vote_announcement.start()
    announce_winner.start()
    monthly_intercommunity_event.start()
    update_leaderboard.start()


@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        reco_channel = discord.utils.get(
            member.guild.text_channels, name=RECOMMENDERS_CHANNEL_NAME
        )
        embed = discord.Embed(
            title=f"Bienvenue, {member.display_name} !",
            description=f"Ce serveur fonctionne par **cooptation**. Pour participer, tu dois être recommandé par un membre existant.\n\n"
            f"Tu peux trouver la liste des membres pouvant te recommander dans {reco_channel.mention if reco_channel else '#' + RECOMMENDERS_CHANNEL_NAME}.",
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
