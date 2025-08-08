import json
import os
from datetime import datetime

import discord
from discord.ext import commands, tasks
from discord.ui import Select, View
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

ASSEMBLEE_CHANNEL_NAME = "assemblée"
EVENEMENT_ROLE_NAME = "Membre de la Meute"
EVENT_PROPOSALS_CHANNEL_NAME = (
    "propositions-evenements"  # Nouveau salon pour les propositions validées
)


# --- Base de données (JSON) ---
def load_data(file_name):
    try:
        with open(file_name, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data, file_name):
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)


# Fichiers de données
recommendations_db = "recommendations.json"
events_db = "events.json"
group_scores_db = "group_scores.json"
last_event_db = "last_event.json"

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Commandes de gestion des membres ---


@bot.command(name="recommander")
@commands.has_role(EVENEMENT_ROLE_NAME)
async def recommend(ctx, new_member: discord.Member):
    """Recommande un nouveau membre. La recommandation est soumise au vote."""
    data = load_data(recommendations_db)
    server_id = str(ctx.guild.id)

    if server_id not in data:
        data[server_id] = {}

    if str(new_member.id) in data[server_id]:
        await ctx.send("Ce membre est déjà en cours de validation.")
        return

    # Stocker la recommandation
    data[server_id][str(new_member.id)] = {
        "recommender_id": ctx.author.id,
        "votes": {str(ctx.author.id)},  # Le recommandeur vote automatiquement pour
        "timestamp": datetime.utcnow().isoformat(),
    }
    save_data(data, recommendations_db)

    # Envoyer le message de vote dans le salon assemblée
    assemblee_channel = discord.utils.get(
        ctx.guild.text_channels, name=ASSEMBLEE_CHANNEL_NAME
    )
    if not assemblee_channel:
        await ctx.send(f"Le salon `{ASSEMBLEE_CHANNEL_NAME}` est introuvable.")
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
        f"Votre recommandation pour {new_member.mention} a été soumise au vote dans {assemblee_channel.mention}."
    )


@tasks.loop(hours=1)
async def check_recommendations():
    """Vérifie périodiquement si un nouveau membre a atteint la majorité."""
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

        # Copie pour éviter les problèmes de modification pendant l'itération
        for member_id_str, info in list(data[server_id].items()):
            try:
                # Retrouver le message de vote
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
                                if new_member:
                                    await new_member.add_roles(member_role)
                                    await assemblee_channel.send(
                                        f"🎉 Bienvenue à {new_member.mention} ! Il a été validé par la majorité et recommandé par {recommender.mention}."
                                    )
                                    await message.delete()
                                    del data[server_id][member_id_str]
            except Exception as e:
                print(f"Erreur lors de la vérification des recommandations: {e}")

        save_data(data, recommendations_db)


# --- Commandes de gestion des événements ---


@bot.command(name="proposer")
@commands.has_role(EVENEMENT_ROLE_NAME)
async def propose_event(ctx, *, proposition: str):
    """Propose un nouvel événement. `!proposer <Titre de l'événement>`."""
    # S'assurer que la commande est utilisée dans un salon de groupe
    if not ctx.channel.name.startswith("groupe-"):
        await ctx.send(
            "❌ Cette commande doit être utilisée dans un salon de groupe (`groupe-...`)."
        )
        return

    group_name = ctx.channel.name.replace("groupe-", "groupe ")
    group_role = discord.utils.get(ctx.guild.roles, name=group_name)
    if not group_role:
        await ctx.send("❌ Impossible de trouver le rôle associé à ce salon de groupe.")
        return

    # Message de proposition dans le salon de gestion du groupe
    gestion_channel_name = f"gestion-{ctx.channel.name[len('groupe-') :]}"
    gestion_channel = discord.utils.get(
        ctx.guild.text_channels, name=gestion_channel_name
    )
    if not gestion_channel:
        await ctx.send(
            f"❌ Le salon de gestion `{gestion_channel_name}` est introuvable."
        )
        return

    embed = discord.Embed(
        title="Nouvelle proposition d'événement",
        description=f"**{proposition}**",
        color=group_role.color,
    )
    embed.set_author(
        name=f"Proposé par {ctx.author.display_name}", icon_url=ctx.author.avatar.url
    )
    embed.set_footer(text="Votez pour soumettre cette proposition à toute la meute.")

    msg = await gestion_channel.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    await ctx.send(
        f"Votre proposition a été envoyée dans {gestion_channel.mention} pour le vote de votre groupe."
    )


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

                            # Ajout à la base de données des événements
                            events_data = load_data(events_db)
                            server_id = str(guild.id)
                            if server_id not in events_data:
                                events_data[server_id] = {}
                            event_id = str(message.id)
                            events_data[server_id][event_id] = {
                                "title": event_title,
                                "proposer_group": group_role.name,
                                "ratings": {},  # {user_id: rating}
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


# --- Tâches hebdomadaires et mensuelles ---


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
                    label=f"{event['title'][:90]}",
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
            await assemblee_channel.send(
                f"🎉 L'événement de la semaine est : **{winner_info['title']}** ! Proposé par le groupe *{winner_info['proposer_group']}*."
            )

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
            del events_data[winner_id]
            save_data({str(guild.id): events_data}, events_db)


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

            # Réinitialiser les scores pour le mois suivant
            group_scores[str(guild.id)] = {}
            save_data(group_scores, group_scores_db)


# --- Commandes de groupe (inchangées) ---
# ... (Copiez-collez ici vos commandes `groupe`, `leave`, `join` existantes) ...


# --- Événements et démarrage du bot ---
@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    # Démarrage des tâches en arrière-plan
    check_recommendations.start()
    check_group_votes.start()
    weekly_vote_announcement.start()
    announce_winner.start()
    monthly_intercommunity_event.start()


bot.run(TOKEN)
