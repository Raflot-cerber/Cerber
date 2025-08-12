# -*- coding: utf-8 -*-

import calendar
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

# --- Noms des Rôles & Salons (Thème "Enfer") ---
# Ces noms doivent correspondre exactement à ceux de votre serveur Discord.
TRIBUNAL_CHANNEL_NAME = "⚖️-tribunal-infernal"
EVENT_PROPOSALS_CHANNEL_NAME = "🔥-pactes-proposés"
WELCOME_CHANNEL_NAME = "👋-portes-de-l-enfer"
RECOMMENDERS_CHANNEL_NAME = "🔑-gardiens-des-clés"
LOG_CHANNEL_NAME_ADMIN = "bot-logs-enfer"
PROFILES_CHANNEL_NAME = "📜-grimoires-des-cercles"
LEADERBOARD_CHANNEL_NAME = "🏆-panthéon-des-damnés"
REGISTRE_CHANNEL_NAME = "⚜️-registre-des-âmes"
CALENDAR_CHANNEL_NAME = "📅-calendrier-des-supplices"  # NOUVEAU SALON

DAMNED_SOUL_ROLE_NAME = "Âme Damnée"  # Ancien "Membre de la Meute"
MONTHLY_WINNER_ROLE_NAME = "🏆 Cercle du Mois"  # Ancien "Groupe du Mois"
MAX_GROUP_MEMBERS = 10  # Nombre maximum de membres par cercle (anciennement groupe)


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
recommendations_db = "recommendations_enfer.json"
events_db = "events_enfer.json"
group_scores_db = "group_scores_enfer.json"
weekly_votes_db = "weekly_votes_enfer.json"


# --- Journal d'actions (Logging) ---
async def log_action(
    guild: discord.Guild, title: str, description: str, color=discord.Color.dark_red()
):
    """Envoie un message de log dans le salon dédié aux admins."""
    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME_ADMIN)
    if log_channel:
        embed = discord.Embed(
            title=f"🔥 Log Infernal : {title}", description=description, color=color
        )
        embed.timestamp = datetime.now()
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
intents.reactions = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("§"), intents=intents)


# =================================================================================
# === FONCTIONS UTILITAIRES
# =================================================================================
async def update_event_proposals_list(guild: discord.Guild):
    """Met à jour le message listant les propositions de pactes (événements)."""
    proposals_channel = discord.utils.get(
        guild.text_channels, name=EVENT_PROPOSALS_CHANNEL_NAME
    )
    if not proposals_channel:
        return

    events_data = load_data(events_db).get(str(guild.id), {})
    active_events = {
        k: v for k, v in events_data.items() if v.get("status") == "active"
    }

    sorted_events = sorted(
        active_events.items(), key=lambda item: item[1]["average_rating"], reverse=True
    )

    embed = discord.Embed(
        title="🔥 Propositions de Pactes Actuelles",
        description="Voici la liste des pactes proposés par les cercles. \nUtilisez `/noter` pour donner votre jugement et influencer le panthéon !",
        color=discord.Color.orange(),
    )

    if not sorted_events:
        embed.description = "Aucun pacte n'est actuellement proposé. Soyez le premier à sceller le vôtre avec la commande `/proposer` !"
    else:
        event_list_str = ""
        for event_id, event in sorted_events:
            event_list_str += (
                f"**{event['title']}** (par *{event['proposer_group'][7:]}*)\n"
                f"> Jugement moyen : **{event['average_rating']:.2f}/5** "
                f"sur {len(event['ratings'])} vote(s)\n"
                f"> ID du Pacte : `{event_id}`\n\n"
            )
        embed.description += "\n\n" + event_list_str

    async for message in proposals_channel.history(limit=50):
        if (
            message.author == bot.user
            and message.embeds
            and message.embeds[0].title == embed.title
        ):
            try:
                await message.edit(embed=embed)
                return
            except discord.NotFound:
                continue

    await proposals_channel.send(embed=embed)


# NOUVELLE FONCTION POUR LE CALENDRIER
async def generate_calendar_embed(guild: discord.Guild, year: int, month: int):
    """Génère l'embed du calendrier pour un mois donné."""
    events_data = load_data(events_db).get(str(guild.id), {})

    # Filtrer les événements qui ont une date et sont validés
    month_events = {}
    for event_id, event in events_data.items():
        if event.get("date") and event.get("status") == "validated":
            event_date = datetime.fromisoformat(event["date"])
            if event_date.year == year and event_date.month == month:
                if event_date.day not in month_events:
                    month_events[event_date.day] = []
                month_events[event_date.day].append(event["title"])

    cal = calendar.Calendar()
    month_days = cal.monthdayscalendar(year, month)

    # Traduction du nom du mois en français
    month_names_fr = [
        "Janvier",
        "Février",
        "Mars",
        "Avril",
        "Mai",
        "Juin",
        "Juillet",
        "Août",
        "Septembre",
        "Octobre",
        "Novembre",
        "Décembre",
    ]
    month_name = month_names_fr[month - 1]

    embed = discord.Embed(
        title=f"📅 Calendrier des Supplices - {month_name} {year}",
        color=discord.Color.dark_purple(),
    )

    week_days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    header = " | ".join([f"**{day}**" for day in week_days])

    cal_str = ""
    for week in month_days:
        week_str = ""
        for day in week:
            if day == 0:
                week_str += " ` ` "  # Espace vide pour les jours hors du mois
            else:
                if day in month_events:
                    week_str += " `🔥` "  # Marqueur pour un jour avec événement
                else:
                    week_str += f" `{day:02d}` "
        cal_str += week_str + "\n"

    embed.add_field(name=header, value=cal_str, inline=False)

    events_list_str = ""
    for day in sorted(month_events.keys()):
        events_list_str += (
            f"**{day:02d}/{month:02d}** : {', '.join(month_events[day])}\n"
        )

    if not events_list_str:
        events_list_str = "Aucun supplice programmé pour ce mois."

    embed.add_field(
        name="Pactes Validés ce Mois-ci", value=events_list_str, inline=False
    )
    embed.set_footer(
        text="Les jours marqués d'un 🔥 ont un ou plusieurs pactes prévus."
    )

    return embed


# =================================================================================
# === COMMANDES SLASH (/)
# =================================================================================


@bot.tree.command(
    name="aide", description="Affiche le grimoire des commandes disponibles."
)
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Grimoire du Bot de l'Enfer",
        description="Voici la liste des commandes slash (/) pour naviguer dans les abysses.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(
        name="🔥 Gestion des Cercles",
        value="`/cercle` : Fonde un nouveau cercle des damnés.\n"
        "`/cercles` : Affiche la liste des cercles à rejoindre.\n"
        "`/rejoindre` : Rejoins un cercle existant.\n"
        "`/quitter` : Quitte votre cercle actuel.\n"
        "`/grimoire` : Met à jour la description de votre cercle.",
        inline=False,
    )
    embed.add_field(
        name="⚖️ Gouvernance Infernale",
        value="`/recommander` : Propose une nouvelle âme pour la damnation.\n"
        "`/bannir` : Lance un vote pour bannir une âme.\n"
        "`/noter` : Juge une proposition de pacte de 1 à 5.",
        inline=False,
    )
    embed.add_field(
        name="📅 Événements & Compétition",
        value="`/proposer` : Ouvre un formulaire pour proposer un nouveau pacte.\n"
        "`/panthéon` : Affiche les classements actuels des damnés.\n"
        "`/calendrier` : Affiche le calendrier des supplices du mois.",
        inline=False,
    )
    embed.set_footer(text="Toutes les commandes commencent par un /")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="cercle", description="Fonde un nouveau cercle avec rôle et salons dédiés."
)
@app_commands.describe(
    nom="Le nom du nouveau cercle.",
    couleur="Le code hexadécimal de la couleur (ex: #660000).",
)
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def cercle(interaction: discord.Interaction, nom: str, couleur: str):
    await interaction.response.defer(ephemeral=True)

    if discord.utils.find(
        lambda r: r.name.startswith("cercle "), interaction.user.roles
    ):
        await interaction.followup.send(
            "❌ Vous appartenez déjà à un cercle. Quittez-le avec `/quitter` pour en fonder un nouveau.",
            ephemeral=True,
        )
        return

    try:
        couleur_obj = discord.Colour.from_str(couleur)
    except ValueError:
        await interaction.followup.send(
            "❌ Le format de la couleur est invalide. Utilisez un code hexadécimal comme `#660000`.",
            ephemeral=True,
        )
        return

    guild = interaction.guild
    role_name = f"cercle {nom}"

    if discord.utils.get(guild.roles, name=role_name):
        await interaction.followup.send(
            f"❌ Un cercle nommé '{nom}' existe déjà dans les abysses.", ephemeral=True
        )
        return

    nouveau_role = await guild.create_role(
        name=role_name,
        colour=couleur_obj,
        reason=f"Fondation du cercle par {interaction.user}",
    )
    await interaction.user.add_roles(nouveau_role)

    categorie = await guild.create_category(f"🔥 CERCLE {nom.upper()}")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        nouveau_role: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, connect=True, speak=True
        ),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    nom_slug = nom.lower().replace(" ", "-")
    await categorie.create_text_channel(f"�-{nom_slug}", overwrites=overwrites)
    await categorie.create_text_channel(
        f"🔒-sanctuaire-{nom_slug}", overwrites=overwrites
    )
    await categorie.create_voice_channel(f"🔊 Murmures - {nom}", overwrites=overwrites)

    await interaction.followup.send(
        f"✅ Le cercle '{nom}' a été fondé et vous en êtes la première âme damnée !",
        ephemeral=True,
    )
    await log_action(
        guild,
        "Fondation de Cercle",
        f"Le cercle **{nom}** a été fondé par {interaction.user.mention}.",
        color=discord.Color.green(),
    )


@bot.tree.command(
    name="cercles",
    description="Affiche la liste de tous les cercles qu'il est possible de rejoindre.",
)
async def cercles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    all_group_roles = [role for role in guild.roles if role.name.startswith("cercle ")]

    embed = discord.Embed(
        title="🔥 Liste des Cercles de l'Enfer",
        description="Voici les cercles que vous pouvez rejoindre. Utilisez `/rejoindre <nom du cercle>`.",
        color=discord.Color.dark_purple(),
    )

    if not all_group_roles:
        embed.description = "Il n'y a aucun cercle à rejoindre pour le moment."
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    joinable_groups_text = ""
    for role in sorted(all_group_roles, key=lambda r: r.name):
        member_count = len(role.members)
        if member_count < MAX_GROUP_MEMBERS:
            places_left = MAX_GROUP_MEMBERS - member_count
            joinable_groups_text += f"**{role.name[7:]}** - `{member_count}/{MAX_GROUP_MEMBERS}` âmes ({places_left} places restantes)\n"

    if not joinable_groups_text:
        embed.add_field(
            name="Cercles disponibles",
            value="Aucun cercle n'a de place pour une nouvelle âme.",
            inline=False,
        )
    else:
        embed.add_field(
            name="Cercles disponibles", value=joinable_groups_text, inline=False
        )

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="rejoindre", description="Rejoins un cercle existant s'il n'est pas complet."
)
@app_commands.describe(nom_cercle="Le nom exact du cercle que tu veux rejoindre.")
async def rejoindre(interaction: discord.Interaction, nom_cercle: str):
    member = interaction.user
    guild = interaction.guild
    role_demande = discord.utils.get(guild.roles, name=f"cercle {nom_cercle}")

    if not role_demande:
        await interaction.response.send_message(
            f"❌ Le cercle '{nom_cercle}' n'existe pas.", ephemeral=True
        )
        return

    if len(role_demande.members) >= MAX_GROUP_MEMBERS:
        await interaction.response.send_message(
            f"❌ Ce cercle est déjà complet ({MAX_GROUP_MEMBERS} âmes).",
            ephemeral=True,
        )
        return

    ancien_role = discord.utils.find(
        lambda r: r.name.startswith("cercle "), member.roles
    )
    if ancien_role:
        await member.remove_roles(ancien_role, reason="Changement de cercle")

    await member.add_roles(role_demande, reason=f"A rejoint le cercle {nom_cercle}")
    await interaction.response.send_message(
        f"✅ Tu as bien rejoint le cercle **{nom_cercle}** !", ephemeral=True
    )


@bot.tree.command(name="quitter", description="Quitte votre cercle actuel.")
async def quitter(interaction: discord.Interaction):
    member = interaction.user
    guild = interaction.guild
    role_groupe = discord.utils.find(
        lambda r: r.name.startswith("cercle "), member.roles
    )

    if not role_groupe:
        await interaction.response.send_message(
            "❌ Tu n'appartiens à aucun cercle.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    nom_groupe_original = role_groupe.name[7:]
    await member.remove_roles(role_groupe, reason="A quitté le cercle")
    await interaction.followup.send(
        f"✅ Tu as quitté le cercle **{nom_groupe_original}**.", ephemeral=True
    )

    role_groupe_updated = guild.get_role(role_groupe.id)
    if role_groupe_updated and len(role_groupe_updated.members) == 0:
        await log_action(
            guild,
            "Purge de Cercle",
            f"Le cercle **{nom_groupe_original}** est vide et va être purgé.",
            color=discord.Color.orange(),
        )

        categorie = discord.utils.get(
            guild.categories, name=f"🔥 CERCLE {nom_groupe_original.upper()}"
        )
        if categorie:
            for channel in categorie.channels:
                try:
                    await channel.delete(reason="Cercle vide")
                except discord.HTTPException as e:
                    print(f"Erreur lors de la suppression du salon {channel.name}: {e}")
            try:
                await categorie.delete(reason="Cercle vide")
            except discord.HTTPException as e:
                print(
                    f"Erreur lors de la suppression de la catégorie {categorie.name}: {e}"
                )

        try:
            await role_groupe_updated.delete(reason="Cercle vide")
            await log_action(
                guild,
                "Cercle Purgé",
                f"Le cercle **{nom_groupe_original}** a été purgé avec succès.",
                color=discord.Color.red(),
            )
        except discord.HTTPException as e:
            print(
                f"Erreur lors de la suppression du rôle {role_groupe_updated.name}: {e}"
            )


@bot.tree.command(
    name="recommander",
    description="Lance un vote pour damner une nouvelle âme.",
)
@app_commands.describe(membre="L'âme que tu souhaites recommander.")
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def recommander(interaction: discord.Interaction, membre: discord.Member):
    data = load_data(recommendations_db)
    server_id = str(interaction.guild.id)
    if server_id not in data:
        data[server_id] = {}

    if str(membre.id) in data[server_id]:
        await interaction.response.send_message(
            "Cette âme est déjà en cours de jugement.", ephemeral=True
        )
        return

    data[server_id][str(membre.id)] = {
        "recommender_id": interaction.user.id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    save_data(data, recommendations_db)

    assemblee_channel = discord.utils.get(
        interaction.guild.text_channels, name=TRIBUNAL_CHANNEL_NAME
    )
    if not assemblee_channel:
        await interaction.response.send_message(
            f"Le salon `{TRIBUNAL_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Nouvelle Recommandation d'Âme",
        description=f"{interaction.user.mention} a recommandé {membre.mention} pour la damnation éternelle.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"ID de l'âme: {membre.id}")
    msg = await assemblee_channel.send(embed=embed)
    await msg.add_reaction("✅")

    await interaction.response.send_message(
        f"Votre recommandation pour {membre.mention} a été soumise au jugement dans {assemblee_channel.mention}.",
        ephemeral=True,
    )
    await log_action(
        interaction.guild,
        "Recommandation",
        f"{interaction.user.mention} a recommandé {membre.mention}.",
        color=discord.Color.blue(),
    )


@bot.tree.command(
    name="bannir", description="Lance un vote pour bannir une âme de l'Enfer."
)
@app_commands.describe(membre="L'âme à bannir.", raison="La raison du bannissement.")
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def bannir(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if membre == interaction.user:
        await interaction.response.send_message(
            "❌ Vous ne pouvez pas vous bannir vous-même.", ephemeral=True
        )
        return
    if membre.bot:
        await interaction.response.send_message(
            "❌ Vous ne pouvez pas bannir un démon inférieur (bot).", ephemeral=True
        )
        return
    if membre.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Vous ne pouvez pas bannir un Archidémon (administrateur).",
            ephemeral=True,
        )
        return

    assemblee_channel = discord.utils.get(
        interaction.guild.text_channels, name=TRIBUNAL_CHANNEL_NAME
    )
    if not assemblee_channel:
        await interaction.response.send_message(
            f"❌ Le salon `{TRIBUNAL_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Vote de Bannissement",
        description=f"{interaction.user.mention} a lancé un vote pour bannir {membre.mention} de l'Enfer.",
        color=discord.Color.red(),
    )
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.set_footer(text=f"ID de l'âme à bannir: {membre.id}")

    msg = await assemblee_channel.send(embed=embed)
    await msg.add_reaction("✅")

    await interaction.response.send_message(
        f"Le vote de bannissement pour {membre.mention} a été lancé dans {assemblee_channel.mention}.",
        ephemeral=True,
    )
    await log_action(
        interaction.guild,
        "Vote de Bannissement Lancé",
        f"{interaction.user.mention} a lancé un vote pour bannir {membre.mention} pour la raison : {raison}.",
        color=discord.Color.dark_red(),
    )


class GroupProfileModal(Modal, title="Mise à jour du Grimoire du Cercle"):
    description = TextInput(
        label="Description de votre cercle",
        style=discord.TextStyle.paragraph,
        placeholder="Décrivez ici la philosophie de votre cercle, vos pactes favoris, etc.",
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
            lambda r: r.name.startswith("cercle "), interaction.user.roles
        )
        if not author_group_role:
            await interaction.followup.send(
                "❌ Vous devez appartenir à un cercle pour utiliser cette commande.",
                ephemeral=True,
            )
            return

        existing_message = None
        async for message in profile_channel.history(limit=100):
            if (
                message.author == bot.user
                and message.embeds
                and message.embeds[0].footer.text
                == f"ID du cercle : {author_group_role.id}"
            ):
                existing_message = message
                break

        embed = discord.Embed(
            title=f"Grimoire du Cercle : {author_group_role.name[7:]}",
            description=self.description.value,
            color=author_group_role.color,
        )
        members_list = "\n".join(
            [f"• {member.display_name}" for member in author_group_role.members]
        )
        embed.add_field(
            name="Âmes Damnées", value=members_list or "Aucune âme", inline=False
        )
        embed.set_footer(text=f"ID du cercle : {author_group_role.id}")

        if existing_message:
            await existing_message.edit(embed=embed)
        else:
            await profile_channel.send(embed=embed)

        await interaction.followup.send(
            "✅ Grimoire du cercle mis à jour !", ephemeral=True
        )


@bot.tree.command(
    name="grimoire",
    description="Définit ou met à jour le message de présentation de votre cercle.",
)
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def grimoire(interaction: discord.Interaction):
    await interaction.response.send_modal(GroupProfileModal())


class ProposeEventModal(Modal, title="Proposer un nouveau Pacte"):
    category = TextInput(
        label="Catégorie du Pacte",
        placeholder="Ex: [Jeu], [Tourment], [Conspiration]...",
        required=True,
    )
    event_title = TextInput(
        label="Titre du Pacte",
        placeholder="Le titre doit être clair et évocateur.",
        required=True,
    )
    description = TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )
    # NOUVEAU CHAMP POUR LA DATE
    event_date = TextInput(
        label="Date du Pacte (JJ/MM/AAAA)",
        placeholder="Format : 25/12/2024",
        required=True,
        min_length=10,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        group_role = discord.utils.find(
            lambda r: r.name.startswith("cercle "), interaction.user.roles
        )
        if not group_role:
            await interaction.response.send_message(
                "❌ Vous devez faire partie d'un cercle.", ephemeral=True
            )
            return

        # Validation de la date
        try:
            date_obj = datetime.strptime(self.event_date.value, "%d/%m/%Y")
        except ValueError:
            await interaction.response.send_message(
                "❌ Format de date invalide. Veuillez utiliser JJ/MM/AAAA.",
                ephemeral=True,
            )
            return

        gestion_slug = group_role.name[7:].lower().replace(" ", "-")
        gestion_channel = discord.utils.get(
            interaction.guild.text_channels, name=f"🔒-sanctuaire-{gestion_slug}"
        )
        if not gestion_channel:
            await interaction.response.send_message(
                "❌ Sanctuaire introuvable pour votre cercle.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Nouvelle proposition de Pacte : {self.event_title.value}",
            color=group_role.color,
        )
        embed.set_author(
            name=f"Proposé par {interaction.user.display_name}",
            icon_url=interaction.user.avatar.url,
        )
        embed.add_field(name="Catégorie", value=self.category.value, inline=False)
        embed.add_field(name="Date proposée", value=self.event_date.value, inline=False)
        if self.description.value:
            embed.add_field(
                name="Description", value=self.description.value, inline=False
            )

        msg = await gestion_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        await interaction.response.send_message(
            f"✅ Proposition de pacte envoyée dans {gestion_channel.mention} pour validation !",
            ephemeral=True,
        )
        await log_action(
            interaction.guild,
            "Proposition de Pacte",
            f"{interaction.user.mention} a proposé `{self.event_title.value}` pour le cercle **{group_role.name}**.",
        )


@bot.tree.command(
    name="proposer", description="Ouvre une fenêtre pour proposer un nouveau pacte."
)
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def proposer(interaction: discord.Interaction):
    await interaction.response.send_modal(ProposeEventModal())


@bot.tree.command(name="noter", description="Juge une proposition de pacte de 1 à 5.")
@app_commands.describe(
    id_pacte="L'ID du pacte à juger.", note="Votre jugement de 1 à 5."
)
@app_commands.choices(
    note=[
        app_commands.Choice(name="⭐ (Médiocre)", value=1),
        app_commands.Choice(name="⭐⭐ (Passable)", value=2),
        app_commands.Choice(name="⭐⭐⭐ (Intéressant)", value=3),
        app_commands.Choice(name="⭐⭐⭐⭐ (Excellent)", value=4),
        app_commands.Choice(name="⭐⭐⭐⭐⭐ (Divin)", value=5),
    ]
)
@app_commands.checks.has_role(DAMNED_SOUL_ROLE_NAME)
async def noter(
    interaction: discord.Interaction, id_pacte: str, note: app_commands.Choice[int]
):
    await interaction.response.defer(ephemeral=True)
    events_data = load_data(events_db)
    server_id = str(interaction.guild.id)

    if server_id not in events_data or id_pacte not in events_data[server_id]:
        await interaction.followup.send(
            "❌ Cet ID de pacte n'existe pas ou n'est plus valide.", ephemeral=True
        )
        return

    event = events_data[server_id][id_pacte]
    event["ratings"][str(interaction.user.id)] = note.value
    total_ratings = sum(event["ratings"].values())
    event["average_rating"] = round(total_ratings / len(event["ratings"]), 2)
    save_data(events_data, events_db)

    await update_event_proposals_list(interaction.guild)
    await interaction.followup.send(
        f'✅ Votre jugement de **{note.value}/5** a bien été pris en compte pour le pacte "{event["title"]}".',
        ephemeral=True,
    )


@bot.tree.command(
    name="panthéon",
    description="Force la mise à jour et l'affichage du Panthéon des Damnés.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def panthéon(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = discord.utils.get(
        interaction.guild.text_channels, name=LEADERBOARD_CHANNEL_NAME
    )
    if channel:
        await update_leaderboard_task()  # Appel direct de la fonction de mise à jour
        await interaction.followup.send("✅ Panthéon mis à jour.", ephemeral=True)
    else:
        await interaction.followup.send(
            f"❌ Le salon `{LEADERBOARD_CHANNEL_NAME}` est introuvable.", ephemeral=True
        )


# NOUVELLE COMMANDE CALENDRIER
@bot.tree.command(
    name="calendrier",
    description="Affiche le calendrier des supplices pour le mois en cours ou un mois spécifique.",
)
@app_commands.describe(
    mois="Le numéro du mois (1-12). Laisse vide pour le mois en cours.",
    annee="L'année (ex: 2024). Laisse vide pour l'année en cours.",
)
async def calendrier(
    interaction: discord.Interaction, mois: int = None, annee: int = None
):
    await interaction.response.defer(ephemeral=True)

    now = datetime.now()
    target_month = mois if mois else now.month
    target_year = annee if annee else now.year

    if not (1 <= target_month <= 12):
        await interaction.followup.send(
            "❌ Le mois doit être un nombre entre 1 et 12.", ephemeral=True
        )
        return

    calendar_channel = discord.utils.get(
        interaction.guild.text_channels, name=CALENDAR_CHANNEL_NAME
    )
    if not calendar_channel:
        await interaction.followup.send(
            f"❌ Le salon `{CALENDAR_CHANNEL_NAME}` est introuvable. Veuillez le créer.",
            ephemeral=True,
        )
        return

    embed = await generate_calendar_embed(interaction.guild, target_year, target_month)

    # Supprime les anciens calendriers avant de poster le nouveau
    async for message in calendar_channel.history(limit=5):
        if (
            message.author == bot.user
            and message.embeds
            and message.embeds[0].title.startswith("📅 Calendrier des Supplices")
        ):
            await message.delete()

    await calendar_channel.send(embed=embed)
    await interaction.followup.send(
        f"✅ Le calendrier a été mis à jour dans {calendar_channel.mention}.",
        ephemeral=True,
    )


# =================================================================================
# === TÂCHES EN ARRIÈRE-PLAN (TASKS)
# =================================================================================


class WeeklyVoteView(View):
    def __init__(self, options, vote_id):
        super().__init__(timeout=172800)  # 48h
        self.vote_id = vote_id
        self.add_item(self.create_select(options))

    def create_select(self, options):
        select = Select(
            placeholder="Choisissez le pacte de la semaine",
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
            "✅ Votre vote a bien été scellé !", ephemeral=True
        )


@tasks.loop(hours=24)
async def weekly_vote_announcement():
    now = datetime.now()
    # Mercredi à 18h
    if now.weekday() == 2 and now.hour == 18:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=TRIBUNAL_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            events_data = load_data(events_db).get(str(guild.id), {})
            eligible_events = {
                k: v for k, v in events_data.items() if v.get("status") == "active"
            }
            if not eligible_events:
                await assemblee_channel.send(
                    "Il n'y a aucun nouveau pacte à juger pour cette semaine."
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
                    description=f"Jugement: {event['average_rating']:.2f}/5",
                    value=event_id,
                )
                for event_id, event in sorted_events[:25]
            ]

            if not options:
                await assemblee_channel.send(
                    "Aucun pacte éligible pour le vote cette semaine."
                )
                return

            temp_msg = await assemblee_channel.send("Préparation du jugement...")
            vote_id = str(temp_msg.id)

            view = WeeklyVoteView(options, vote_id)
            await temp_msg.edit(
                content="⚖️ **Jugement de la Semaine !**\nChoisissez le pacte qui sera honoré parmi les propositions :",
                view=view,
            )


@tasks.loop(hours=24)
async def announce_winner():
    now = datetime.now()
    # Vendredi à 20h
    if now.weekday() == 4 and now.hour == 20:
        for guild in bot.guilds:
            assemblee_channel = discord.utils.get(
                guild.text_channels, name=TRIBUNAL_CHANNEL_NAME
            )
            if not assemblee_channel:
                continue

            votes_data = load_data(weekly_votes_db)
            if not votes_data:
                return

            latest_vote_id = sorted(votes_data.keys())[-1]
            latest_votes = votes_data[latest_vote_id]

            if not latest_votes:
                await assemblee_channel.send("Aucune âme n'a voté cette semaine !")
                return

            vote_counts = Counter(latest_votes.values())
            winner_id, _ = vote_counts.most_common(1)[0]

            events_data = load_data(events_db)
            server_id = str(guild.id)
            winner_info = events_data.get(server_id, {}).get(winner_id)

            if not winner_info:
                print(f"Erreur: L'ID du pacte gagnant {winner_id} est introuvable.")
                continue

            # Le statut passe à 'validated' au lieu de 'past' pour le calendrier
            events_data[server_id][winner_id]["status"] = "validated"
            save_data(events_data, events_db)

            winner_category = winner_info.get("category", "[Autre]")
            announcement_text = f"🎉 Le pacte de la semaine est : **{winner_category} {winner_info['title']}** ! Proposé par le cercle *{winner_info['proposer_group'][7:]}*."
            announcement_message = await assemblee_channel.send(announcement_text)

            try:
                thread_name = f"Débriefing sur - {winner_info['title']}"[:100]
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

            await update_event_proposals_list(guild)
            await update_calendar_task()  # Mise à jour du calendrier

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
                guild.text_channels, name=TRIBUNAL_CHANNEL_NAME
            )
            if assemblee_channel:
                embed = discord.Embed(
                    title="🏆 Cérémonie Infernale du Mois ! 🏆",
                    description=f"Ce mois-ci, le cercle **{winning_group_name[7:]}** est à l'honneur avec un score de **{score}** pactes validés !\n\nIls organiseront la prochaine grande cérémonie et reçoivent le rôle honorifique.",
                    color=discord.Color.gold(),
                )
                await assemblee_channel.send(embed=embed)

            if winning_group_role and winner_role:
                for member in winning_group_role.members:
                    await member.add_roles(winner_role, reason="Cercle gagnant du mois")

            # Réinitialisation des scores
            group_scores[str(guild.id)] = {}
            save_data(group_scores, group_scores_db)
            await update_leaderboard_task()  # Met à jour le classement après reset


# Fonction séparée pour la mise à jour du leaderboard pour pouvoir l'appeler directement
async def update_leaderboard_task():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=LEADERBOARD_CHANNEL_NAME)
        if channel:
            # Purge les anciens messages du bot dans le salon
            async for message in channel.history(limit=10):
                if message.author == bot.user:
                    await message.delete()
            embed = await generate_leaderboard_embed(guild)
            await channel.send(embed=embed)


@tasks.loop(hours=6)
async def update_leaderboard_loop():
    await update_leaderboard_task()


# NOUVELLE TÂCHE POUR LE CALENDRIER
async def update_calendar_task():
    await bot.wait_until_ready()
    now = datetime.now()
    for guild in bot.guilds:
        calendar_channel = discord.utils.get(
            guild.text_channels, name=CALENDAR_CHANNEL_NAME
        )
        if calendar_channel:
            embed = await generate_calendar_embed(guild, now.year, now.month)
            # Supprime l'ancien calendrier
            async for message in calendar_channel.history(limit=5):
                if message.author == bot.user:
                    await message.delete()
            await calendar_channel.send(embed=embed)


@tasks.loop(hours=1)
async def update_calendar_loop():
    await update_calendar_task()


async def generate_leaderboard_embed(guild: discord.Guild):
    embed = discord.Embed(title="🏆 Panthéon des Damnés 🏆", color=discord.Color.gold())

    group_scores = load_data(group_scores_db).get(str(guild.id), {})
    sorted_groups = sorted(group_scores.items(), key=lambda item: item[1], reverse=True)
    group_text = "\n".join(
        [
            f"**{i + 1}.** {name[7:]} ({score} pts)"
            for i, (name, score) in enumerate(sorted_groups[:5])
        ]
    )
    embed.add_field(
        name="Top Cercles du Mois",
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
            f"**{i + 1}.** <@{user_id}> ({count} jugements)"
            for i, (user_id, count) in enumerate(top_raters)
        ]
    )
    embed.add_field(
        name="Âmes les Plus Actives",
        value=raters_text or "Personne n'a encore jugé de pacte.",
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

    print("Démarrage des tâches infernales...")
    weekly_vote_announcement.start()
    announce_winner.start()
    monthly_intercommunity_event.start()
    update_leaderboard_loop.start()
    update_calendar_loop.start()  # Démarrage de la tâche calendrier

    for guild in bot.guilds:
        await update_event_proposals_list(guild)
        await update_calendar_task()  # Mise à jour initiale au démarrage


@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        reco_channel = discord.utils.get(
            member.guild.text_channels, name=RECOMMENDERS_CHANNEL_NAME
        )
        embed = discord.Embed(
            title=f"Bienvenue en Enfer, {member.display_name} !",
            description=f"Ce royaume fonctionne par **cooptation**. Pour devenir une âme damnée, tu dois être recommandé par un Gardien des Clés.\n\n"
            f"Tu peux trouver la liste des gardiens pouvant t'ouvrir les portes dans {reco_channel.mention if reco_channel else '#' + RECOMMENDERS_CHANNEL_NAME}.",
            color=discord.Color.dark_red(),
        )
        await channel.send(content=member.mention, embed=embed)


@bot.event
async def on_member_remove(member):
    """Nettoie une recommandation en attente si l'âme quitte le serveur."""
    data = load_data(recommendations_db)
    server_id = str(member.guild.id)
    member_id_str = str(member.id)

    if server_id in data and member_id_str in data[server_id]:
        del data[server_id][member_id_str]
        save_data(data, recommendations_db)
        await log_action(
            member.guild,
            "Purge de Recommandation",
            f"La recommandation en attente pour **{member.display_name}** a été purgée car l'âme a quitté l'Enfer.",
            color=discord.Color.dark_grey(),
        )


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return
    if not (message.author == bot.user and message.embeds):
        return

    embed = message.embeds[0]

    # --- GESTION DES VOTES DANS LE TRIBUNAL ---
    if channel.name == TRIBUNAL_CHANNEL_NAME and str(payload.emoji) == "✅":
        member_role = discord.utils.get(guild.roles, name=DAMNED_SOUL_ROLE_NAME)
        if not member_role:
            return

        total_members = len(member_role.members)
        majority_needed = (total_members // 2) + 1

        reaction = discord.utils.get(message.reactions, emoji="✅")
        if not (reaction and reaction.count >= majority_needed):
            return

        # --- CAS 1: VOTE DE RECOMMANDATION ---
        if embed.title == "Nouvelle Recommandation d'Âme":
            member_id_str = embed.footer.text.split(": ")[1]
            data = load_data(recommendations_db)
            server_id = str(guild.id)
            info = data.get(server_id, {}).get(member_id_str)
            if not info:
                return

            new_member = guild.get_member(int(member_id_str))
            recommender = guild.get_member(info["recommender_id"])

            if new_member and recommender:
                await new_member.add_roles(member_role)
                await channel.send(
                    f"🎉 La recommandation pour {new_member.mention} a été validée ! L'âme est damnée."
                )

                registre_channel = discord.utils.get(
                    guild.text_channels, name=REGISTRE_CHANNEL_NAME
                )
                if registre_channel:
                    await registre_channel.send(
                        f"🔥 Bienvenue à {new_member.mention}, qui rejoint les damnés sur recommandation de {recommender.mention}."
                    )

                await log_action(
                    guild,
                    "Âme Validée",
                    f"{new_member.mention} a été validé par {recommender.mention}.",
                    color=discord.Color.green(),
                )
                await message.delete()

                del data[server_id][member_id_str]
                save_data(data, recommendations_db)

        # --- CAS 2: VOTE DE BANNISSEMENT ---
        elif embed.title == "Vote de Bannissement":
            member_id_str = embed.footer.text.split(": ")[1]
            member_to_kick = guild.get_member(int(member_id_str))

            if member_to_kick:
                try:
                    await member_to_kick.kick(reason="Banni par vote du tribunal.")
                    await channel.send(
                        f"✅ Le jugement est terminé. {member_to_kick.mention} a été banni de l'Enfer."
                    )
                    await log_action(
                        guild,
                        "Âme Bannie",
                        f"{member_to_kick.mention} a été banni par vote.",
                        color=discord.Color.red(),
                    )
                except discord.Forbidden:
                    await channel.send(
                        f"❌ Je n'ai pas le pouvoir de bannir {member_to_kick.mention}."
                    )
                    await log_action(
                        guild,
                        "Erreur de Bannissement",
                        f"Tentative de bannissement de {member_to_kick.mention} échouée.",
                        color=discord.Color.orange(),
                    )
            await message.delete()

    # --- GESTION DES VOTES DE PROPOSITION DE PACTE ---
    if channel.name.startswith("🔒-sanctuaire-"):
        group_name_slug = channel.name[len("🔒-sanctuaire-") :]
        group_role = discord.utils.find(
            lambda r: r.name[7:].lower().replace(" ", "-") == group_name_slug,
            guild.roles,
        )
        if not group_role or not group_role.members:
            return

        member_count = len(group_role.members)
        majority_needed = (member_count // 2) + 1

        yes_reac = discord.utils.get(message.reactions, emoji="✅")
        no_reac = discord.utils.get(message.reactions, emoji="❌")

        voters_yes = (
            [user async for user in yes_reac.users() if not user.bot]
            if yes_reac
            else []
        )
        voters_no = (
            [user async for user in no_reac.users() if not user.bot] if no_reac else []
        )

        if str(payload.emoji) == "✅" and len(voters_yes) >= majority_needed:
            event_title = embed.title[len("Nouvelle proposition de Pacte : ") :]
            category_field = discord.utils.get(embed.fields, name="Catégorie")
            date_field = discord.utils.get(embed.fields, name="Date proposée")

            event_category = category_field.value if category_field else "[Autre]"
            event_date_str = date_field.value if date_field else None

            event_date_iso = None
            if event_date_str:
                try:
                    event_date_iso = datetime.strptime(
                        event_date_str, "%d/%m/%Y"
                    ).isoformat()
                except ValueError:
                    await channel.send(
                        "Date invalide dans la proposition, elle ne sera pas ajoutée au calendrier.",
                        delete_after=30,
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
                "average_rating": 0.0,
                "status": "active",
                "date": event_date_iso,  # Ajout de la date
            }
            save_data(events_data, events_db)

            await channel.send(
                f'✅ Le pacte "{event_title}" a été validé par le cercle et est maintenant soumis au jugement de tous !',
                delete_after=60,
            )
            await update_event_proposals_list(guild)
            await message.delete()

        elif str(payload.emoji) == "❌" and len(voters_no) >= majority_needed:
            await channel.send(
                f'Le pacte "{embed.title[len("Nouvelle proposition de Pacte : ") :]}" a été rejeté par le cercle.',
                delete_after=60,
            )
            await message.delete()


# --- Démarrage du Bot ---
if __name__ == "__main__":
    if TOKEN is None:
        print(
            "Erreur : Le token Discord n'est pas défini. Veuillez créer un fichier .env avec DISCORD_TOKEN=votretokendeconnexion"
        )
    else:
        bot.run(TOKEN)
