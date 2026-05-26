"""
cogs/social.py — Leaderboard, trade system, and server news feed
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    leaderboard_embed, error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import get_item, format_eddies


class SocialCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /leaderboard ──────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="View the top players in Night City.")
    @app_commands.describe(sort="Sort by which metric (default: level).")
    @app_commands.choices(sort=[
        app_commands.Choice(name="Level", value="level"),
        app_commands.Choice(name="Street Cred", value="street_cred"),
        app_commands.Choice(name="Eddies (Wealth)", value="eddies"),
        app_commands.Choice(name="Total XP", value="total_xp"),
    ])
    async def leaderboard(self, interaction: discord.Interaction, sort: app_commands.Choice[str] = None):
        sort_by = sort.value if sort else "level"
        top_players = await self.db.get_leaderboard(sort_by=sort_by, limit=10)
        if not top_players:
            await interaction.response.send_message(
                embed=info_embed("No Data", "No players found yet.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        sort_name = sort.name if sort else "Level"
        embed = leaderboard_embed(top_players, sort_name)
        await interaction.response.send_message(embed=embed)

    # ── /trade offer ──────────────────────────────────────────
    trade_group = app_commands.Group(name="trade", description="Player trading system.")

    @trade_group.command(name="offer", description="Offer a trade to another player.")
    @app_commands.describe(
        target="The player to trade with.",
        give_item="The item ID you are offering.",
        give_qty="Quantity of item you're offering (default: 1).",
        want_item="The item ID you want in return (optional).",
        want_eddies="Amount of eddies you want in return (optional).",
    )
    async def trade_offer(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        give_item: str,
        give_qty: int = 1,
        want_item: str = None,
        want_eddies: int = 0,
    ):
        if target.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Invalid", "Can't trade with yourself."), ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message(embed=error_embed("Invalid", "Can't trade with a bot."), ephemeral=True)
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

        give_item = give_item.lower().replace(" ", "_")
        inv = await self.db.get_inventory_item(str(interaction.user.id), give_item)
        if not inv or inv["quantity"] < give_qty:
            await interaction.response.send_message(
                embed=error_embed("Item Not Found", f"You don't have {give_qty}x `{give_item}` in your inventory."),
                ephemeral=True
            )
            return

        give_item_data = get_item(give_item)
        give_name = give_item_data["name"] if give_item_data else give_item

        want_item_id = want_item.lower().replace(" ", "_") if want_item else None
        want_item_data = get_item(want_item_id) if want_item_id else None
        want_name = want_item_data["name"] if want_item_data else (want_item_id or "")

        trade_id = await self.db.create_trade_offer(
            from_id=str(interaction.user.id),
            to_id=str(target.id),
            give_item=give_item,
            give_qty=give_qty,
            want_item=want_item_id,
            want_eddies=max(0, want_eddies),
        )

        # Build trade summary
        give_line = f"**{give_qty}x {give_name}**"
        want_lines = []
        if want_item_id:
            want_lines.append(f"**{want_name}**")
        if want_eddies > 0:
            want_lines.append(f"**{want_eddies:,} €$**")
        want_str = " + ".join(want_lines) if want_lines else "*Nothing (gift)*"

        embed = discord.Embed(
            title="🤝 TRADE OFFER SENT",
            description=(
                f"{interaction.user.mention} offers {target.mention} a trade:\n\n"
                f"**Offering:** {give_line}\n"
                f"**Wants:** {want_str}\n\n"
                f"**Trade ID:** `{trade_id}`\n"
                f"{target.mention}, use `/trade accept {trade_id}` to accept or `/trade decline {trade_id}` to decline."
            ),
            color=config.COLORS["cyan"]
        )
        await interaction.response.send_message(embed=embed)

    @trade_group.command(name="accept", description="Accept a trade offer.")
    @app_commands.describe(trade_id="The trade ID to accept.")
    async def trade_accept(self, interaction: discord.Interaction, trade_id: int):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        trade = await self.db.get_trade_offer(trade_id)
        if not trade:
            await interaction.response.send_message(
                embed=error_embed("Not Found", f"Trade `{trade_id}` doesn't exist."),
                ephemeral=True
            )
            return

        if trade["to_id"] != str(interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Not Your Trade", "This trade offer is not for you."),
                ephemeral=True
            )
            return

        if trade["status"] != "pending":
            await interaction.response.send_message(
                embed=error_embed("Trade Closed", "This trade is no longer active."),
                ephemeral=True
            )
            return

        from_player = await self.db.get_player(trade["from_id"])
        if not from_player:
            await interaction.response.send_message(
                embed=error_embed("Offer Expired", "The other player's character no longer exists."),
                ephemeral=True
            )
            return

        # Verify from player still has the item
        from_inv = await self.db.get_inventory_item(trade["from_id"], trade["give_item"])
        if not from_inv or from_inv["quantity"] < trade["give_qty"]:
            await interaction.response.send_message(
                embed=error_embed("Trade Invalid", "The offering player no longer has the required items."),
                ephemeral=True
            )
            return

        # Verify acceptor has want_item (if any)
        if trade["want_item"]:
            acc_inv = await self.db.get_inventory_item(str(interaction.user.id), trade["want_item"])
            if not acc_inv or acc_inv["quantity"] < 1:
                want_item_data = get_item(trade["want_item"])
                name = want_item_data["name"] if want_item_data else trade["want_item"]
                await interaction.response.send_message(
                    embed=error_embed("Missing Item", f"You need **{name}** to complete this trade."),
                    ephemeral=True
                )
                return

        # Verify acceptor has eddies
        if trade["want_eddies"] > 0 and player["eddies"] < trade["want_eddies"]:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds", f"This trade requires **{trade['want_eddies']:,} €$**."),
                ephemeral=True
            )
            return

        # Execute trade
        await self.db.remove_item(trade["from_id"], trade["give_item"], trade["give_qty"])
        await self.db.add_item(str(interaction.user.id), trade["give_item"], trade["give_qty"])

        if trade["want_item"]:
            await self.db.remove_item(str(interaction.user.id), trade["want_item"], 1)
            await self.db.add_item(trade["from_id"], trade["want_item"], 1)

        if trade["want_eddies"] > 0:
            await self.db.add_eddies(str(interaction.user.id), -trade["want_eddies"])
            await self.db.add_eddies(trade["from_id"], trade["want_eddies"])

        await self.db.close_trade_offer(trade_id, "accepted")

        give_item_data = get_item(trade["give_item"])
        give_name = give_item_data["name"] if give_item_data else trade["give_item"]

        embed = success_embed(
            "Trade Complete!",
            f"**{trade['give_qty']}x {give_name}** has been transferred.\n*Both parties have received their goods.*"
        )
        await interaction.response.send_message(embed=embed)

    @trade_group.command(name="decline", description="Decline a trade offer.")
    @app_commands.describe(trade_id="The trade ID to decline.")
    async def trade_decline(self, interaction: discord.Interaction, trade_id: int):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        trade = await self.db.get_trade_offer(trade_id)
        if not trade:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Trade `{trade_id}` doesn't exist."), ephemeral=True)
            return

        if trade["to_id"] != str(interaction.user.id) and trade["from_id"] != str(interaction.user.id):
            await interaction.response.send_message(embed=error_embed("Not Your Trade", "You're not part of this trade."), ephemeral=True)
            return

        await self.db.close_trade_offer(trade_id, "declined")
        await interaction.response.send_message(
            embed=info_embed("Trade Declined", f"Trade `{trade_id}` has been declined.", config.COLORS["yellow"])
        )

    @trade_group.command(name="list", description="View your pending trade offers.")
    async def trade_list(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        trades = await self.db.get_pending_trades(str(interaction.user.id))
        if not trades:
            await interaction.response.send_message(
                embed=info_embed("No Trades", "You have no pending trade offers.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🤝 YOUR TRADE OFFERS",
            color=config.COLORS["cyan"]
        )
        for t in trades[:10]:
            give_item_data = get_item(t["give_item"])
            give_name = give_item_data["name"] if give_item_data else t["give_item"]
            direction = "📤 Sent to" if t["from_id"] == str(interaction.user.id) else "📥 Received from"
            other_id = t["to_id"] if t["from_id"] == str(interaction.user.id) else t["from_id"]
            other_player = await self.db.get_player(other_id)
            other_name = other_player["username"] if other_player else "Unknown"
            embed.add_field(
                name=f"ID {t['id']} — {direction} {other_name}",
                value=f"Offering: {t['give_qty']}x **{give_name}** | Status: {t['status']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /news ─────────────────────────────────────────────────
    @app_commands.command(name="news", description="View the latest news and events from Night City.")
    async def news(self, interaction: discord.Interaction):
        # Fetch recent events from the DB — last 10 notable actions
        recent = await self.db.get_recent_events(limit=10)

        embed = discord.Embed(
            title="📡 NIGHT CITY NEWS — NC54",
            description="*All the gonk that's fit to broadcast.*",
            color=config.COLORS["yellow"]
        )

        if not recent:
            embed.add_field(
                name="Breaking News",
                value="Night City is quiet for once. Too quiet.",
                inline=False
            )
        else:
            for event in recent:
                embed.add_field(
                    name=event.get("headline", "Unknown Event"),
                    value=event.get("body", ""),
                    inline=False
                )

        embed.set_footer(text="NC54 — The city that never sleeps. Neither do we.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialCog(bot))
