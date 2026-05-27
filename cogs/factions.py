"""
cogs/factions.py — Faction standings, street cred, and player bounties
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    factions_embed, error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import format_eddies


class FactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /factions ─────────────────────────────────────────────
    @app_commands.command(name="factions", description="View your reputation with all Night City factions.")
    async def factions_view(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        faction_rep = await self.db.get_faction_rep(str(interaction.user.id))
        # Convert list to dict for factions_embed
        faction_rep_dict = {row["faction_id"]: row["reputation"] for row in faction_rep}
        embed = factions_embed(player, faction_rep_dict)
        await interaction.response.send_message(embed=embed)

    # ── /streetcred ───────────────────────────────────────────
    @app_commands.command(name="streetcred", description="View your Street Cred and Night City reputation title.")
    async def streetcred(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        from utils.helpers import make_progress_bar
        cred = player["street_cred"]
        title = config.get_street_cred_title(cred)
        # Next title threshold
        titles = config.STREET_CRED_TITLES
        next_threshold = None
        for t in titles:
            if t["min_cred"] > cred:
                next_threshold = t
                break

        embed = discord.Embed(
            title="🏆 STREET CRED",
            color=config.COLORS["yellow"]
        )
        embed.add_field(name="Your Title", value=f"**{title}**", inline=True)
        embed.add_field(name="Street Cred", value=f"**{cred:,}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        if next_threshold:
            needed = next_threshold["min_cred"] - cred
            pct = cred / next_threshold["min_cred"]
            bar = make_progress_bar(min(1.0, pct), 15)
            embed.add_field(
                name=f"Next: {next_threshold['title']}",
                value=f"{bar}\n{needed:,} more cred needed",
                inline=False
            )
        else:
            embed.add_field(name="Status", value="Maximum reputation reached. Night City knows your name.", inline=False)

        embed.add_field(
            name="🔒 Unlocks",
            value=(
                f"• **10+ Cred** — Black Market access\n"
                f"• **25+ Cred** — Better gig payouts\n"
                f"• **50+ Cred** — Legendary vendor items\n"
                f"• **100+ Cred** — Fixer-tier missions"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    # ── /pledge ───────────────────────────────────────────────
    @app_commands.command(name="pledge", description="Pledge your loyalty to a faction for bonuses.")
    @app_commands.describe(faction="The faction to pledge loyalty to.")
    @app_commands.choices(faction=[
        app_commands.Choice(name="Maelstrom", value="maelstrom"),
        app_commands.Choice(name="Tyger Claws", value="tyger_claws"),
        app_commands.Choice(name="Valentinos", value="valentinos"),
        app_commands.Choice(name="6th Street", value="6th_street"),
        app_commands.Choice(name="Animals", value="animals"),
        app_commands.Choice(name="Voodoo Boys", value="voodoo_boys"),
        app_commands.Choice(name="Militech", value="militech"),
        app_commands.Choice(name="Arasaka", value="arasaka"),
        app_commands.Choice(name="Aldecaldos", value="aldecaldos"),
        app_commands.Choice(name="Moxes", value="moxes"),
    ])
    async def pledge(self, interaction: discord.Interaction, faction: app_commands.Choice[str]):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        faction_rep = await self.db.get_faction_rep(str(interaction.user.id))
        rep_row = next((r for r in faction_rep if r["faction_id"] == faction.value), None)
        rep = rep_row["reputation"] if rep_row else 0

        if rep < config.FACTION_PLEDGE_REQ:
            await interaction.response.send_message(
                embed=error_embed(
                    "Insufficient Reputation",
                    f"You need at least **{config.FACTION_PLEDGE_REQ} reputation** with {faction.name} to pledge loyalty.\n"
                    f"You have **{rep}**."
                ),
                ephemeral=True
            )
            return

        current_pledge = player.get("pledged_faction", "")
        if current_pledge == faction.value:
            await interaction.response.send_message(
                embed=info_embed("Already Pledged", f"You're already pledged to **{faction.name}**.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        await self.db.update_player(str(interaction.user.id), pledged_faction=faction.value)
        faction_info = config.FACTIONS.get(faction.value, {})
        bonus = faction_info.get("pledge_bonus", "Faction loyalty bonus")

        embed = success_embed(
            "Loyalty Pledged",
            f"You've pledged loyalty to **{faction_info.get('emoji','🏴')} {faction.name}**!\n\n"
            f"**Bonus:** {bonus}\n\n"
            f"*Gang members will recognize you. Enemies of {faction.name} will not forget.*"
        )
        await interaction.response.send_message(embed=embed)

    # ── /bounty place ─────────────────────────────────────────
    bounty_group = app_commands.Group(name="bounty", description="Player bounty system.")

    @bounty_group.command(name="place", description="Place a bounty on another player.")
    @app_commands.describe(
        target="The player to place a bounty on.",
        amount="Amount of eddies to offer as the bounty.",
        reason="Reason for the bounty (optional)."
    )
    async def bounty_place(self, interaction: discord.Interaction, target: discord.Member, amount: int, reason: str = "No reason given."):
        if target.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Invalid", "You can't put a bounty on yourself."), ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message(embed=error_embed("Invalid", "Can't bounty a bot."), ephemeral=True)
            return

        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        target_player = await self.db.get_player(str(target.id))
        if not target_player:
            await interaction.response.send_message(
                embed=error_embed("Not Found", f"{target.display_name} doesn't have a character."),
                ephemeral=True
            )
            return

        min_bounty = config.MIN_BOUNTY_AMOUNT
        if amount < min_bounty:
            await interaction.response.send_message(
                embed=error_embed("Bounty Too Low", f"Minimum bounty is **{min_bounty:,} €$**."),
                ephemeral=True
            )
            return

        if player["eddies"] < amount:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds", f"You don't have **{amount:,} €$** to place as a bounty."),
                ephemeral=True
            )
            return

        await self.db.add_eddies(str(interaction.user.id), -amount)
        await self.db.place_bounty(
            placer_id=str(interaction.user.id),
            target_id=str(target.id),
            amount=amount,
            reason=reason[:200]
        )

        embed = discord.Embed(
            title="🎯 BOUNTY PLACED",
            description=(
                f"A bounty of **{amount:,} €$** has been placed on **{target.display_name}**.\n\n"
                f"**Reason:** {reason}\n\n"
                f"*Any player who defeats them in a duel will collect the bounty.*"
            ),
            color=config.COLORS["red"]
        )
        embed.set_footer(text="The streets will know.")
        await interaction.response.send_message(embed=embed)

    # ── /bounty list ──────────────────────────────────────────
    @bounty_group.command(name="list", description="View all active bounties on players.")
    async def bounty_list(self, interaction: discord.Interaction):
        bounties = await self.db.get_all_bounties()
        if not bounties:
            await interaction.response.send_message(
                embed=info_embed("No Active Bounties", "There are no active bounties right now.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎯 ACTIVE BOUNTIES",
            description="*Night City's most wanted. Take them down and collect.*",
            color=config.COLORS["red"]
        )
        for i, b in enumerate(bounties[:10], 1):
            target_name = b.get("target_username", "Unknown")
            amount = b.get("total_amount", 0)
            reason = b.get("latest_reason", "No reason given")
            embed.add_field(
                name=f"#{i} — {target_name}",
                value=f"💰 **{amount:,} €$** | *{reason[:80]}*",
                inline=False
            )

        embed.set_footer(text="Defeat a bounty target in /duel to collect their bounty.")
        await interaction.response.send_message(embed=embed)

    # ── /bounty on ────────────────────────────────────────────
    @bounty_group.command(name="on", description="Check bounties on a specific player.")
    @app_commands.describe(target="The player to check bounties on.")
    async def bounty_on(self, interaction: discord.Interaction, target: discord.Member):
        bounties = await self.db.get_bounties_on(str(target.id))
        if not bounties:
            await interaction.response.send_message(
                embed=info_embed("No Bounties", f"There are no bounties on **{target.display_name}**.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        total = sum(b["amount"] for b in bounties)
        embed = discord.Embed(
            title=f"🎯 Bounties on {target.display_name}",
            description=f"**Total Bounty: {total:,} €$**",
            color=config.COLORS["red"]
        )
        for b in bounties[:5]:
            placer = b.get("placer_username", "Unknown")
            reason = b.get("reason", "No reason")
            embed.add_field(
                name=f"{b['amount']:,} €$ — by {placer}",
                value=f"*{reason[:100]}*",
                inline=False
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FactionsCog(bot))
