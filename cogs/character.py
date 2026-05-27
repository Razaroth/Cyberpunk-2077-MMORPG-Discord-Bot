"""
cogs/character.py — Character creation, profile, leveling, and daily rewards
"""
from __future__ import annotations

from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

import config
from utils.embeds import (
    profile_embed, stats_embed, error_embed, success_embed,
    info_embed, not_registered_embed
)
from utils.helpers import format_eddies


# ─────────────────────────────────────────────────────────────
#  Character Creation UI
# ─────────────────────────────────────────────────────────────
class LifepathSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["name"],
                value=key,
                description=info["description"][:100],
                emoji=info["emoji"]
            )
            for key, info in config.LIFEPATHS.items()
        ]
        super().__init__(placeholder="Choose your lifepath...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.view is None:
            return
        self.view.selected_lifepath = self.values[0]
        lp = config.LIFEPATHS[self.values[0]]
        
        # Defer to acknowledge the interaction
        await interaction.response.defer()
        
        # Update the button state internally
        self.view.confirm_btn.disabled = False
        
        # Send confirmation message
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"{lp['emoji']} {lp['name']} Selected",
                description=(
                    f"{lp['description']}\n\n"
                    f"**Bonus:** {lp['starting_bonus']}\n"
                    f"**Starting Eddies:** {lp['starting_eddies']:,} €$\n\n"
                    f"Click **Confirm** below to begin your life in Night City."
                ),
                color=config.COLORS["yellow"]
            ),
            view=self.view,
            ephemeral=True
        )


class ConfirmCharacterButton(discord.ui.Button):
    def __init__(self, db):
        super().__init__(
            label="Confirm — Begin in Night City",
            style=discord.ButtonStyle.danger,
            emoji="🔴",
            disabled=True
        )
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not isinstance(view, CharacterCreationView):
            await interaction.response.send_message("Error: Invalid view", ephemeral=True)
            return
        if not view.selected_lifepath:
            await interaction.response.send_message("Please select a lifepath first!", ephemeral=True)
            return

        db = self.db
        if await db.player_exists(str(interaction.user.id)):
            await interaction.response.send_message(
                embed=error_embed("Already Registered", "You already have a character! Use `/profile` to view it."),
                ephemeral=True
            )
            return

        lp_key = view.selected_lifepath
        lp = config.LIFEPATHS[lp_key]

        # Base attributes — lifepath gives +1 to one stat
        attrs = {"body": 3, "reflexes": 3, "tech": 3, "intelligence": 3, "cool": 3}
        bonus_attr = lp.get("bonus_attr")
        if bonus_attr and bonus_attr in attrs:
            attrs[bonus_attr] += 1

        await db.create_player(
            user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            lifepath=lp_key,
            body=attrs["body"],
            reflexes=attrs["reflexes"],
            tech=attrs["tech"],
            intelligence=attrs["intelligence"],
            cool=attrs["cool"],
            starting_eddies=lp["starting_eddies"],
            starting_location=lp["starting_location"]
        )

        # Give starting equipment
        starting_items = {"street_kid": "lexington", "nomad": "baseball_bat", "corpo": "nue"}
        starting_weapon = starting_items.get(lp_key, "lexington")
        await db.add_item(str(interaction.user.id), starting_weapon, 1)
        await db.add_item(str(interaction.user.id), "leather_jacket", 1)
        await db.add_item(str(interaction.user.id), "maxdoc_mk1", 3)

        if view:
            view.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🏙️ Welcome to Night City, {interaction.user.display_name}",
                description=(
                    f"**Lifepath:** {lp['emoji']} {lp['name']}\n\n"
                    f"{lp['description']}\n\n"
                    f"**Starting Gear:**\n"
                    f"• Weapon issued\n"
                    f"• Leather Jacket\n"
                    f"• MaxDoc Mk.1 ×3\n\n"
                    f"**Starting Eddies:** {lp['starting_eddies']:,} €$\n\n"
                    f"*Type `/profile` to see your character. Type `/explore` to begin.*\n"
                    f"*The city doesn't care about you. Prove it wrong.*"
                ),
                color=config.COLORS["yellow"]
            ),
            view=None
        )


class CharacterCreationView(discord.ui.View):
    def __init__(self, db):
        super().__init__(timeout=120)
        self.selected_lifepath: str = ""
        self.confirm_btn = ConfirmCharacterButton(db)
        self.add_item(LifepathSelect())
        self.add_item(self.confirm_btn)


# ─────────────────────────────────────────────────────────────
#  Attribute Upgrade View
# ─────────────────────────────────────────────────────────────
class AttributeUpgradeSelect(discord.ui.Select):
    def __init__(self, player: dict, db):
        options = []
        for attr_key, attr_info in config.ATTRIBUTES.items():
            current = player[attr_key]
            if current < config.MAX_ATTRIBUTE:
                options.append(discord.SelectOption(
                    label=f"{attr_info['name']} ({current} → {current+1})",
                    value=attr_key,
                    description=attr_info["description"][:100],
                    emoji=attr_info["emoji"]
                ))
        if not options:
            options = [discord.SelectOption(label="All attributes maxed", value="none")]
        super().__init__(placeholder="Select attribute to upgrade...", options=options, min_values=1, max_values=1)
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("All attributes are already at max!", ephemeral=True)
            return
        db = self.db
        player = await db.get_player(str(interaction.user.id))
        if not player or player.get("attr_points", 0) < 1:
            await interaction.response.send_message("No attribute points available!", ephemeral=True)
            return
        attr = self.values[0]
        new_val = player[attr] + 1
        updates: dict = {attr: new_val, "attr_points": player["attr_points"] - 1}
        # Body increases max HP
        if attr == "body":
            updates["max_health"] = player["max_health"] + config.HP_PER_BODY_POINT
        await db.update_player(str(interaction.user.id), **updates)
        attr_info = config.ATTRIBUTES[attr]
        if self.view:
            self.view.stop()
        await interaction.response.edit_message(
            embed=success_embed(
                "Attribute Upgraded!",
                f"{attr_info['emoji']} **{attr_info['name']}** increased to **{new_val}**!\n"
                f"Remaining attribute points: {player['attr_points'] - 1}"
            ),
            view=None
        )


class AttributeUpgradeView(discord.ui.View):
    def __init__(self, player: dict, db):
        super().__init__(timeout=60)
        self.add_item(AttributeUpgradeSelect(player, db))


# ─────────────────────────────────────────────────────────────
#  The Cog
# ─────────────────────────────────────────────────────────────
class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore

    # ── /start ────────────────────────────────────────────────
    @app_commands.command(name="start", description="Create your character and begin your life in Night City.")
    async def start(self, interaction: discord.Interaction):
        if await self.db.player_exists(str(interaction.user.id)):
            await interaction.response.send_message(
                embed=error_embed("Already Registered", "You already have a character. Use `/profile` to view it."),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏙️ NIGHT CITY AWAITS",
            description=(
                "**Welcome to Night City.**\n\n"
                "This city eats people alive. Dreams, bodies, and souls — "
                "all equally disposable. But sometimes, someone claws their way to the top.\n\n"
                "Who were you before you got here?\n\n"
                "*Choose your **Lifepath** — it determines your background, "
                "bonus attributes, and starting conditions.*"
            ),
            color=config.COLORS["yellow"]
        )
        embed.set_footer(text="Your choices define who you are. Choose wisely.")
        view = CharacterCreationView(self.db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /profile ──────────────────────────────────────────────
    @app_commands.command(name="profile", description="View your character profile.")
    @app_commands.describe(user="View another player's profile (optional).")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        player = await self.db.get_player(str(target.id))
        if not player:
            if user:
                await interaction.response.send_message(
                    embed=error_embed("Not Found", f"{target.display_name} doesn't have a character."),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        equipped = await self.db.get_equipped_items(str(target.id))
        faction_rep = await self.db.get_faction_rep(str(target.id))
        # discord.Member is a subclass of discord.User, so it's compatible
        embed = profile_embed(player, target, equipped, faction_rep)  # type: ignore
        await interaction.response.send_message(embed=embed)

    # ── /stats ────────────────────────────────────────────────
    @app_commands.command(name="stats", description="View your attribute stats and available points.")
    async def stats(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        await interaction.response.send_message(embed=stats_embed(player))

    # ── /levelup ──────────────────────────────────────────────
    @app_commands.command(name="levelup", description="Spend attribute points to upgrade your stats.")
    async def levelup(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        if player.get("attr_points", 0) < 1:
            await interaction.response.send_message(
                embed=info_embed(
                    "No Attribute Points",
                    "You don't have any attribute points to spend.\nLevel up by earning XP in combat and missions!",
                    config.COLORS["cyan"]
                ),
                ephemeral=True
            )
            return
        embed = discord.Embed(
            title="⬆️ Level Up — Choose an Attribute",
            description=f"You have **{player['attr_points']}** attribute point(s) to spend.",
            color=config.COLORS["yellow"]
        )
        view = AttributeUpgradeView(player, self.db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /daily ────────────────────────────────────────────────
    @app_commands.command(name="daily", description="Claim your daily rewards — eddies and XP.")
    async def daily(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        last = player.get("last_daily")
        if last:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            hours_passed = (now - last_dt).total_seconds() / 3600
            if hours_passed < config.DAILY_COOLDOWN_HOURS:
                remaining = config.DAILY_COOLDOWN_HOURS - hours_passed
                h = int(remaining)
                m = int((remaining - h) * 60)
                await interaction.response.send_message(
                    embed=error_embed(
                        "Already Claimed",
                        f"You've already claimed your daily reward.\n"
                        f"Come back in **{h}h {m}m**."
                    ),
                    ephemeral=True
                )
                return

        eddies = config.DAILY_EDDIES + player["level"] * 50
        xp = config.DAILY_XP + player["level"] * 20

        await self.db.add_eddies(str(interaction.user.id), eddies)
        level_result = await self.db.add_xp(str(interaction.user.id), xp)
        await self.db.update_player(str(interaction.user.id), last_daily=now.isoformat())

        level_text = ""
        if level_result.get("leveled_up"):
            level_text = f"\n\n🎉 **LEVEL UP!** You are now Level **{level_result['new_level']}**!"

        embed = discord.Embed(
            title="📦 Daily Reward Claimed!",
            description=(
                f"*The city gives nothing for free. But today, you got lucky.*\n\n"
                f"💰 **+{eddies:,} €$** Eddies\n"
                f"⭐ **+{xp:,} XP**{level_text}\n\n"
                f"*Come back tomorrow for another reward.*"
            ),
            color=config.COLORS["green"]
        )
        await interaction.response.send_message(embed=embed)

    # ── /heal ─────────────────────────────────────────────────
    @app_commands.command(name="heal", description="Use a MaxDoc or BounceBack from your inventory to heal.")
    async def heal(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        if player["health"] >= player["max_health"]:
            await interaction.response.send_message(
                embed=info_embed("Already Full Health", "You're already at maximum HP.", config.COLORS["green"]),
                ephemeral=True
            )
            return

        # Try consumables in priority order
        heal_items = [
            ("maxdoc_mk3", 150), ("bounceback_mk3", 120),
            ("maxdoc_mk2", 80), ("bounceback_mk1", 30),
            ("maxdoc_mk1", 40),
        ]
        for item_id, heal_amt in heal_items:
            inv = await self.db.get_inventory_item(str(interaction.user.id), item_id)
            if inv and inv["quantity"] > 0:
                await self.db.remove_item(str(interaction.user.id), item_id, 1)
                await self.db.heal_player(str(interaction.user.id), heal_amt)
                updated = await self.db.get_player(str(interaction.user.id))
                from utils.helpers import get_item
                item = get_item(item_id)
                embed = success_embed(
                    "Healed",
                    f"Used **{item['name'] if item else item_id}** — healed **{heal_amt} HP**\n"
                    f"HP: {updated['health']}/{updated['max_health']}"
                )
                await interaction.response.send_message(embed=embed)
                return

        await interaction.response.send_message(
            embed=error_embed("No Healing Items", "You have no MaxDoc or BounceBack items.\nBuy some at a shop with `/shop`."),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCog(bot))
