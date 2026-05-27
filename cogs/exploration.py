"""
cogs/exploration.py — Travel, explore, map, and random events
"""
from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    map_embed, location_embed, error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import (
    get_location, get_district, get_random_event, all_location_ids,
    location_choices, format_eddies, get_item
)


class ChoiceEventView(discord.ui.View):
    """View for handling choice events with outcome buttons."""
    
    def __init__(self, bot: commands.Bot, user_id: str, event: dict, embed: discord.Embed):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        self.event = event
        self.embed = embed
        self.outcomes = event.get("outcomes", {})
        self.processed = False
        
        # Create buttons for each outcome
        for choice_key, outcome_data in self.outcomes.items():
            button = discord.ui.Button(
                label=choice_key.replace("_", " ").title(),
                custom_id=f"choice_{choice_key}",
                style=discord.ButtonStyle.primary if choice_key == "help" else discord.ButtonStyle.secondary
            )
            button.callback = lambda interaction, key=choice_key, data=outcome_data: self._process_choice(interaction, key, data)
            self.add_item(button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the user who triggered the event to interact."""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                embed=error_embed("Not Your Event", "This is not your event to interact with."),
                ephemeral=True
            )
            return False
        return True
    
    async def _process_choice(self, interaction: discord.Interaction, choice_key: str, outcome_data: dict):
        """Process the chosen outcome."""
        if self.processed:
            await interaction.response.send_message(
                embed=error_embed("Already Processed", "This choice has already been made."),
                ephemeral=True
            )
            return
        
        self.processed = True
        await interaction.response.defer()
        
        player = await self.bot.db.get_player(self.user_id)
        if not player:
            await interaction.followup.send(
                embed=error_embed("Error", "Could not load your player data."),
                ephemeral=True
            )
            return
        
        # Process costs
        cost_item = outcome_data.get("cost_item")
        if cost_item:
            inventory = await self.bot.db.get_inventory(self.user_id)
            has_item = any(row["item_id"] == cost_item for row in inventory)
            
            if not has_item:
                # Not enough resources
                item_data = get_item(cost_item)
                item_name = item_data["name"] if item_data else cost_item
                self.embed.add_field(
                    name="❌ Choice Failed",
                    value=f"You don't have a **{item_name}** to complete this action.",
                    inline=False
                )
                self.embed.color = config.COLORS["red"]
                await interaction.followup.edit_message(interaction.message.id, embed=self.embed)
                return
            
            # Consume the item
            await self.bot.db.remove_item(self.user_id, cost_item, 1)
        
        # Process rewards
        reward_lines = []
        
        reward_xp = outcome_data.get("reward_xp", 0)
        if reward_xp > 0:
            result = await self.bot.db.add_xp(self.user_id, reward_xp)
            reward_lines.append(f"⭐ +**{reward_xp:,} XP**")
            if result.get("leveled_up"):
                reward_lines.append(f"🎉 **LEVEL UP!** Now Level **{result['new_level']}**!")
        
        faction_rep = outcome_data.get("faction_rep", {})
        for faction, rep_amount in faction_rep.items():
            await self.bot.db.update_faction_rep(self.user_id, faction, rep_amount)
            reward_lines.append(f"🤝 +**{rep_amount}** rep with {faction.replace('_', ' ').title()}")
        
        reward_eddies = outcome_data.get("reward_eddies", 0)
        if reward_eddies > 0:
            await self.bot.db.add_eddies(self.user_id, reward_eddies)
            reward_lines.append(f"💰 +**{reward_eddies:,} €$**")
        
        reward_street_cred = outcome_data.get("reward_street_cred", 0)
        if reward_street_cred > 0:
            await self.bot.db.add_street_cred(self.user_id, reward_street_cred)
            reward_lines.append(f"🏆 +**{reward_street_cred}** Street Cred")
        
        # Build result embed
        self.embed.add_field(
            name=f"✅ {choice_key.replace('_', ' ').title()}",
            value="You made your choice.",
            inline=False
        )
        
        if cost_item:
            item_data = get_item(cost_item)
            item_name = item_data["name"] if item_data else cost_item
            self.embed.add_field(
                name="💸 Cost",
                value=f"Used: {item_data['icon'] if item_data else '📦'} **{item_name}**",
                inline=False
            )
        
        if reward_lines:
            self.embed.add_field(
                name="🎁 Rewards",
                value="\n".join(reward_lines),
                inline=False
            )
        else:
            self.embed.add_field(
                name="📝 Result",
                value="No immediate rewards.",
                inline=False
            )
        
        self.embed.color = config.COLORS["green"]
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.followup.edit_message(interaction.message.id, embed=self.embed, view=self)


class ExplorationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /map ──────────────────────────────────────────────────
    @app_commands.command(name="map", description="View the Night City map and your current location.")
    async def map_cmd(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        await interaction.response.send_message(embed=map_embed(player))

    # ── /location ─────────────────────────────────────────────
    @app_commands.command(name="location", description="View details about your current location.")
    async def location_cmd(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        loc = get_location(player["location"])
        if not loc:
            await interaction.response.send_message(
                embed=error_embed("Unknown Location", f"Could not find data for location: `{player['location']}`"),
                ephemeral=True
            )
            return
        await interaction.response.send_message(embed=location_embed(loc))

    # ── /travel ───────────────────────────────────────────────
    @app_commands.command(name="travel", description="Travel to another location in Night City.")
    @app_commands.describe(destination="The location to travel to.")
    @app_commands.choices(destination=[app_commands.Choice(name=n, value=v) for n, v in location_choices()])
    async def travel(self, interaction: discord.Interaction, destination: app_commands.Choice[str]):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        if player["location"] == destination.value:
            await interaction.response.send_message(
                embed=info_embed("Already Here", f"You're already at **{destination.name}**.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        # Travel cost based on district distance
        travel_cost = config.TRAVEL_COST
        if player["eddies"] < travel_cost:
            await interaction.response.send_message(
                embed=error_embed("Not Enough Eddies", f"Traveling costs **{travel_cost:,} €$**. You only have **{player['eddies']:,} €$**."),
                ephemeral=True
            )
            return

        await self.db.add_eddies(str(interaction.user.id), -travel_cost)
        await self.db.update_player(str(interaction.user.id), location=destination.value)

        loc = get_location(destination.value)
        desc = loc.get("description", "") if loc else ""
        district_id = destination.value.split("_")[0] if loc is None else loc.get("district", "")
        district = get_district(district_id or destination.value.split("_")[0])
        district_emoji = district.get("emoji", "🏙️") if district else "🏙️"

        embed = discord.Embed(
            title=f"{district_emoji} Arrived: {destination.name}",
            description=(
                f"*{desc}*\n\n"
                f"**Travel fee paid:** {travel_cost:,} €$\n"
                f"**Remaining:** {player['eddies'] - travel_cost:,} €$\n\n"
                f"Use `/explore` to search for opportunities, `/shop` to visit vendors."
            ),
            color=config.COLORS.get(district.get("color_key", "cyan"), config.COLORS["cyan"]) if district else config.COLORS["cyan"]
        )
        await interaction.response.send_message(embed=embed)

    # ── /explore ──────────────────────────────────────────────
    @app_commands.command(name="explore", description="Explore your current location for random events and opportunities.")
    async def explore(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        # Check combat — can't explore mid-fight
        combat = await self.db.get_player_combat(str(interaction.user.id))
        if combat:
            await interaction.response.send_message(
                embed=error_embed("In Combat", "You can't explore while in combat!"),
                ephemeral=True
            )
            return

        event = get_random_event(player["location"])
        if not event:
            await interaction.response.send_message(
                embed=info_embed("All Quiet", "Nothing interesting is happening here right now. Try again later.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        event_type = event.get("type", "nothing")
        event_name = event.get("name", "Unknown Event")
        event_desc = event.get("description", "Something happens.")
        emoji = event.get("emoji", "🔍")

        embed = discord.Embed(
            title=f"{emoji} {event_name}",
            description=event_desc,
            color=config.COLORS["yellow"]
        )

        if event_type == "loot":
            eddies = random.randint(*event.get("eddies_range", [50, 200]))
            items = event.get("items", [])
            await self.db.add_eddies(str(interaction.user.id), eddies)
            for item_id in items:
                await self.db.add_item(str(interaction.user.id), item_id, 1)
            reward_lines = [f"💰 +**{eddies:,} €$**"]
            for item_id in items:
                from utils.helpers import get_item
                itm = get_item(item_id)
                reward_lines.append(f"• {itm['icon'] if itm else '📦'} {itm['name'] if itm else item_id}")
            embed.add_field(name="📦 Found", value="\n".join(reward_lines), inline=False)
            embed.color = config.COLORS["green"]

        elif event_type == "xp":
            xp = random.randint(*event.get("xp_range", [50, 150]))
            result = await self.db.add_xp(str(interaction.user.id), xp)
            embed.add_field(name="⭐ Reward", value=f"+**{xp:,} XP**", inline=False)
            if result.get("leveled_up"):
                embed.add_field(name="🎉 LEVEL UP!", value=f"Now Level **{result['new_level']}**!", inline=False)
            embed.color = config.COLORS["green"]

        elif event_type == "cred":
            cred = event.get("street_cred", 2)
            await self.db.add_street_cred(str(interaction.user.id), cred)
            embed.add_field(name="🏆 Street Cred", value=f"+**{cred}** Street Cred", inline=False)
            embed.color = config.COLORS["cyan"]

        elif event_type == "ambush":
            # Trigger a random enemy encounter notice
            hp_loss = random.randint(15, 40)
            new_hp = max(1, player["health"] - hp_loss)
            await self.db.update_player(str(interaction.user.id), health=new_hp)
            embed.add_field(
                name="⚠️ Ambush!",
                value=f"You took **{hp_loss} damage** trying to escape!\nHP: {new_hp}/{player['max_health']}\n\nUse `/hunt` if you want to fight back.",
                inline=False
            )
            embed.color = config.COLORS["red"]

        elif event_type == "faction_rep":
            faction = event.get("faction", "")
            rep = event.get("rep", 5)
            if faction:
                await self.db.update_faction_rep(str(interaction.user.id), faction, rep)
                embed.add_field(
                    name="🤝 Faction Standing",
                    value=f"+**{rep}** reputation with {faction.replace('_', ' ').title()}",
                    inline=False
                )
            embed.color = config.COLORS["cyan"]

        elif event_type == "shop_discount":
            # Placeholder — just flavor text
            embed.add_field(
                name="💡 Tip",
                value="You found a vendor with discounted wares! Visit `/shop` to see what's available.",
                inline=False
            )

        elif event_type == "choice":
            # Choice event with outcomes
            embed.add_field(
                name="⚠️ What do you do?",
                value="Choose an option below to determine the outcome.",
                inline=False
            )
            embed.color = config.COLORS["orange"]
            view = ChoiceEventView(self.bot, str(interaction.user.id), event, embed)
            await interaction.response.send_message(embed=embed, view=view)
            return

        else:
            # Flavor event — nothing mechanical
            embed.add_field(name="📝 Journal", value="*You noted this in your memory shard.*", inline=False)

        await interaction.response.send_message(embed=embed)

    # ── /scan ─────────────────────────────────────────────────
    @app_commands.command(name="scan", description="Use your Kiroshi optics or intelligence to scan your environment.")
    async def scan(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        loc = get_location(player["location"])
        cyberware = await self.db.get_cyberware(str(interaction.user.id))
        has_kiroshi = any("kiroshi" in row["cyberware_id"] for row in cyberware)
        intel = player["intelligence"]
        scan_quality = "basic"
        if has_kiroshi:
            scan_quality = "enhanced"
        if intel >= 8 or (has_kiroshi and intel >= 5):
            scan_quality = "advanced"

        embed = discord.Embed(
            title="👁️ SCANNING ENVIRONMENT",
            color=config.COLORS["cyan"]
        )

        from utils.helpers import get_enemies_for_location
        enemies = get_enemies_for_location(player["location"])
        enemy_names = [e.get("name", "Unknown") for _, e in enemies[:3]] if enemies else []

        if scan_quality in ("enhanced", "advanced"):
            embed.add_field(
                name="👾 Hostiles Detected",
                value="\n".join(f"• {n}" for n in enemy_names) if enemy_names else "Area appears clear",
                inline=False
            )

        if loc:
            shops = loc.get("shops", [])
            embed.add_field(
                name="🏪 Vendors",
                value="\n".join(f"• {s.replace('_', ' ').title()}" for s in shops) if shops else "No vendors nearby",
                inline=False
            )
            if scan_quality == "advanced":
                events = loc.get("events", [])
                embed.add_field(
                    name="⚡ Activity",
                    value=f"Detected {len(events)} types of random events in this area",
                    inline=False
                )

        embed.add_field(
            name="📡 Scan Quality",
            value=f"**{scan_quality.title()}** (Intelligence: {intel}" + (", Kiroshi Optics" if has_kiroshi else "") + ")",
            inline=False
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ExplorationCog(bot))
