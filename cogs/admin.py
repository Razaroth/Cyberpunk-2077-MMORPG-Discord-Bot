"""
cogs/admin.py — Administrator commands for bot management
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import error_embed, success_embed, info_embed
from utils.helpers import get_item


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    admin_group = app_commands.Group(name="admin", description="Administrator commands.")
    admin_group.default_member_permissions = discord.Permissions(administrator=True)

    @admin_group.command(name="give", description="Give eddies to a player.")
    @app_commands.describe(user="The player to give eddies to.", amount="Amount of eddies to give.")
    async def admin_give(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message(embed=error_embed("Invalid", "Amount must be positive."), ephemeral=True)
            return

        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(
                embed=error_embed("Not Found", f"{user.display_name} doesn't have a character."),
                ephemeral=True
            )
            return

        await self.db.add_eddies(str(user.id), amount)
        await interaction.response.send_message(
            embed=success_embed("Eddies Given", f"Gave **{amount:,} €$** to **{user.display_name}**."),
            ephemeral=True
        )

    @admin_group.command(name="setlevel", description="Set a player's level.")
    @app_commands.describe(user="The player.", level="New level (1-50).")
    async def admin_setlevel(self, interaction: discord.Interaction, user: discord.Member, level: int):
        if not 1 <= level <= config.MAX_LEVEL:
            await interaction.response.send_message(
                embed=error_embed("Invalid", f"Level must be between 1 and {config.MAX_LEVEL}."),
                ephemeral=True
            )
            return

        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        xp_required = config.XP_REQUIREMENTS.get(level, 0)
        await self.db.update_player(str(user.id), level=level, xp=xp_required)
        await interaction.response.send_message(
            embed=success_embed("Level Set", f"**{user.display_name}** is now Level **{level}**."),
            ephemeral=True
        )

    @admin_group.command(name="reset", description="Reset a player's character (removes all data).")
    @app_commands.describe(user="The player to reset.")
    async def admin_reset(self, interaction: discord.Interaction, user: discord.Member):
        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        # Confirm with button
        class ConfirmResetView(discord.ui.View):
            def __init__(self, db, target_id: str, target_name: str):
                super().__init__(timeout=30)
                self.db = db
                self.target_id = target_id
                self.target_name = target_name

            @discord.ui.button(label="⚠️ Confirm Reset", style=discord.ButtonStyle.danger)
            async def confirm(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if not btn_interaction.user.guild_permissions.administrator:
                    await btn_interaction.response.send_message("Admins only!", ephemeral=True)
                    return
                await self.db.delete_player(self.target_id)
                self.stop()
                await btn_interaction.response.edit_message(
                    embed=success_embed("Player Reset", f"**{self.target_name}**'s character has been deleted."),
                    view=None
                )

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.stop()
                await btn_interaction.response.edit_message(
                    embed=info_embed("Cancelled", "Reset cancelled.", config.COLORS["cyan"]),
                    view=None
                )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirm Character Reset",
                description=f"This will permanently delete **{user.display_name}**'s character and all associated data. This cannot be undone.",
                color=config.COLORS["red"]
            ),
            view=ConfirmResetView(self.db, str(user.id), user.display_name),
            ephemeral=True
        )

    @admin_group.command(name="heal", description="Fully heal a player.")
    @app_commands.describe(user="The player to heal.")
    async def admin_heal(self, interaction: discord.Interaction, user: discord.Member):
        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        await self.db.full_heal(str(user.id))
        await interaction.response.send_message(
            embed=success_embed("Player Healed", f"**{user.display_name}** has been fully healed."),
            ephemeral=True
        )

    @admin_group.command(name="giveitem", description="Give an item to a player.")
    @app_commands.describe(user="The player.", item_id="Item ID to give.", quantity="Quantity (default: 1).")
    async def admin_giveitem(self, interaction: discord.Interaction, user: discord.Member, item_id: str, quantity: int = 1):
        item_id = item_id.lower().replace(" ", "_")
        item_data = get_item(item_id)
        if not item_data:
            await interaction.response.send_message(
                embed=error_embed("Unknown Item", f"Item `{item_id}` not found."),
                ephemeral=True
            )
            return

        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        if quantity < 1:
            quantity = 1

        await self.db.add_item(str(user.id), item_id, quantity)
        await interaction.response.send_message(
            embed=success_embed("Item Given", f"Gave **{quantity}x {item_data['name']}** to **{user.display_name}**."),
            ephemeral=True
        )

    @admin_group.command(name="givecred", description="Give Street Cred to a player.")
    @app_commands.describe(user="The player.", amount="Amount of street cred to give.")
    async def admin_givecred(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        await self.db.add_street_cred(str(user.id), amount)
        await interaction.response.send_message(
            embed=success_embed("Street Cred Given", f"Gave **{amount}** Street Cred to **{user.display_name}**."),
            ephemeral=True
        )

    @admin_group.command(name="sethumanity", description="Set a player's humanity rating.")
    @app_commands.describe(user="The player.", humanity="New humanity value (0-100).")
    async def admin_sethumanity(self, interaction: discord.Interaction, user: discord.Member, humanity: int):
        humanity = max(0, min(config.MAX_HUMANITY, humanity))
        player = await self.db.get_player(str(user.id))
        if not player:
            await interaction.response.send_message(embed=error_embed("Not Found", "Player not found."), ephemeral=True)
            return

        await self.db.update_player(str(user.id), humanity=humanity)
        await interaction.response.send_message(
            embed=success_embed("Humanity Set", f"**{user.display_name}**'s humanity set to **{humanity}**."),
            ephemeral=True
        )

    @admin_group.command(name="spawn", description="Spawn a server-wide event or announcement.")
    @app_commands.describe(event_type="Type of event to spawn.", message="Custom message for the event.")
    @app_commands.choices(event_type=[
        app_commands.Choice(name="Gang War", value="gang_war"),
        app_commands.Choice(name="Airdrop", value="airdrop"),
        app_commands.Choice(name="Corporate Raid", value="corporate_raid"),
        app_commands.Choice(name="Cyberpsycho Loose", value="cyberpsycho"),
        app_commands.Choice(name="MaxTac Patrol", value="maxtac"),
    ])
    async def admin_spawn(self, interaction: discord.Interaction, event_type: app_commands.Choice[str], message: str = ""):
        event_data = {
            "gang_war": {
                "title": "🔫 GANG WAR ERUPTS",
                "desc": "Multiple factions are clashing in the streets. Combat XP is doubled for 30 minutes!",
                "color": config.COLORS["red"],
            },
            "airdrop": {
                "title": "📦 AIRDROP DETECTED",
                "desc": "A corporate supply drop has landed in Night City. The next 5 players to `/explore` get bonus loot!",
                "color": config.COLORS["green"],
            },
            "corporate_raid": {
                "title": "🏢 CORPORATE RAID",
                "desc": "Militech and Arasaka forces are moving through the city. High-value enemy spawns active!",
                "color": config.COLORS["cyan"],
            },
            "cyberpsycho": {
                "title": "🚨 CYBERPSYCHO ON THE LOOSE",
                "desc": "A cyberpsycho has been reported in Night City. MAXTAC has been dispatched. Civilians advised to shelter in place.",
                "color": config.COLORS["red"],
            },
            "maxtac": {
                "title": "⚠️ MAXTAC PATROL ACTIVE",
                "desc": "MaxTac is patrolling Night City. High humanity players gain bonus street cred. Cyberpsychos beware.",
                "color": config.COLORS["yellow"],
            },
        }

        data = event_data.get(event_type.value, {
            "title": "📢 SERVER EVENT",
            "desc": "A special event is happening in Night City!",
            "color": config.COLORS["yellow"],
        })

        embed = discord.Embed(
            title=data["title"],
            description=(f"*{message}*\n\n" if message else "") + data["desc"],
            color=data["color"]
        )
        embed.set_footer(text=f"Event triggered by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    @admin_group.command(name="stats", description="View bot statistics.")
    async def admin_stats(self, interaction: discord.Interaction):
        total_players = await self.db.get_player_count()
        active_combats = await self.db.get_active_combat_count()

        embed = discord.Embed(title="📊 BOT STATISTICS", color=config.COLORS["cyan"])
        embed.add_field(name="Total Players", value=str(total_players), inline=True)
        embed.add_field(name="Active Combats", value=str(active_combats), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
