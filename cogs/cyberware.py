"""
cogs/cyberware.py — Cyberware installation, removal, ripperdoc, and humanity meter
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    cyberware_embed, error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import (
    get_cyberware, get_item, get_rarity_emoji, get_location, format_eddies
)


SLOT_DISPLAY = {
    "ocular": "👁️ Ocular",
    "arms": "💪 Arms",
    "skeleton": "🦴 Skeleton",
    "circulatory": "❤️ Circulatory",
    "integumentary": "🧥 Integumentary (Skin)",
    "nervous_system": "⚡ Nervous System",
    "operating_system": "💻 Operating System",
    "face": "😷 Face",
    "immune_system": "🛡️ Immune System",
}


class CyberwareCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /cyberware ────────────────────────────────────────────
    @app_commands.command(name="cyberware", description="View your installed cyberware and humanity meter.")
    async def cyberware_view(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        installed = await self.db.get_cyberware(str(interaction.user.id))
        embed = cyberware_embed(player, installed)
        await interaction.response.send_message(embed=embed)

    # ── /humanity ─────────────────────────────────────────────
    @app_commands.command(name="humanity", description="Check your humanity rating and cyberpsychosis risk.")
    async def humanity(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        humanity = player.get("humanity", 100)
        max_humanity = config.MAX_HUMANITY
        pct = humanity / max_humanity
        from utils.helpers import make_progress_bar
        bar = make_progress_bar(pct, 15)

        if humanity >= 80:
            status = "✅ Stable"
            color = config.COLORS["green"]
            desc = "Your humanity is healthy. You're still yourself."
        elif humanity >= 60:
            status = "⚠️ Stressed"
            color = config.COLORS["yellow"]
            desc = "The chrome is taking a toll. Watch yourself, choom."
        elif humanity >= 40:
            status = "🟠 Compromised"
            color = 0xFF8C00
            desc = "The boundary between you and the machine is blurring."
        elif humanity >= 20:
            status = "🔴 Critical"
            color = config.COLORS["red"]
            desc = "You're on the edge. MaxTac might be watching."
        else:
            status = "💀 CYBERPSYCHOSIS"
            color = config.COLORS["red"]
            desc = "You've lost yourself to the chrome. You are a threat to Night City."

        embed = discord.Embed(
            title="🧠 HUMANITY METER",
            description=f"*{desc}*",
            color=color
        )
        embed.add_field(
            name=f"Humanity: {humanity}/{max_humanity} — {status}",
            value=bar,
            inline=False
        )

        installed = await self.db.get_cyberware(str(interaction.user.id))
        if installed:
            cw_lines = []
            for row in installed:
                cw = get_cyberware(row["cyberware_id"])
                if cw:
                    cw_lines.append(f"• {cw['name']}: -{cw.get('humanity_loss', 0)} humanity")
            if cw_lines:
                embed.add_field(
                    name="🔧 Installed Cyberware",
                    value="\n".join(cw_lines[:10]),
                    inline=False
                )

        embed.add_field(
            name="💡 Restoring Humanity",
            value="• Visit a Therapist (not yet implemented)\n• Reduce cyberware with `/cyberware remove`\n• Humanity cannot exceed the maximum",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    # ── /ripperdoc ────────────────────────────────────────────
    @app_commands.command(name="ripperdoc", description="Visit the ripperdoc to browse cyberware upgrades.")
    async def ripperdoc(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        loc = get_location(player["location"])
        if not loc or "ripperdoc" not in loc.get("shops", []):
            await interaction.response.send_message(
                embed=error_embed(
                    "No Ripperdoc Here",
                    "There's no ripperdoc in this area.\nTravel to a location with a ripperdoc, like Watson Kabuki or Westbrook Japantown."
                ),
                ephemeral=True
            )
            return

        from utils.helpers import load_data
        all_cw = load_data("cyberware.json")
        installed = await self.db.get_cyberware(str(interaction.user.id))
        installed_ids = {row["cyberware_id"] for row in installed}

        embed = discord.Embed(
            title="🔬 RIPPERDOC — CYBERWARE CATALOG",
            description=(
                f"*Need some chrome? You've come to the right place.*\n\n"
                f"**Your Humanity:** {player.get('humanity', 100)}/{config.MAX_HUMANITY}\n"
                f"**Your Eddies:** {player['eddies']:,} €$\n\n"
                f"Use `/install <cyberware_id>` to install an upgrade."
            ),
            color=config.COLORS["cyan"]
        )

        for slot, cw_dict in all_cw.items():
            if slot == "_schema":
                continue
            slot_name = SLOT_DISPLAY.get(slot, slot.title())
            lines = []
            for cw_id, cw in cw_dict.items():
                if cw_id in installed_ids:
                    lines.append(f"✅ ~~{cw['name']}~~ (installed)")
                elif player["level"] < cw.get("required_level", 1):
                    lines.append(f"🔒 {cw['name']} (Lv.{cw['required_level']})")
                elif player["tech"] < cw.get("required_tech", 0):
                    lines.append(f"🔒 {cw['name']} (Tech {cw['required_tech']})")
                else:
                    rarity_e = get_rarity_emoji(cw.get("rarity", "common"))
                    lines.append(f"{rarity_e} **{cw['name']}** — {cw['cost']:,} €$ | -{cw['humanity_loss']} humanity | `{cw_id}`")
            if lines:
                embed.add_field(name=slot_name, value="\n".join(lines[:5]), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /install ──────────────────────────────────────────────
    @app_commands.command(name="install", description="Install cyberware from a ripperdoc.")
    @app_commands.describe(cyberware_id="The cyberware ID to install (from /ripperdoc list).")
    async def install(self, interaction: discord.Interaction, cyberware_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        loc = get_location(player["location"])
        if not loc or "ripperdoc" not in loc.get("shops", []):
            await interaction.response.send_message(
                embed=error_embed("No Ripperdoc", "You need to be near a ripperdoc to install cyberware."),
                ephemeral=True
            )
            return

        cyberware_id = cyberware_id.lower().replace(" ", "_")
        cw = get_cyberware(cyberware_id)
        if not cw:
            await interaction.response.send_message(
                embed=error_embed("Unknown Cyberware", f"Cyberware `{cyberware_id}` not found. Check `/ripperdoc` for available options."),
                ephemeral=True
            )
            return

        # Level/tech requirements
        if player["level"] < cw.get("required_level", 1):
            await interaction.response.send_message(
                embed=error_embed("Level Too Low", f"**{cw['name']}** requires Level **{cw['required_level']}**."),
                ephemeral=True
            )
            return
        if player["tech"] < cw.get("required_tech", 0):
            await interaction.response.send_message(
                embed=error_embed("Insufficient Tech", f"**{cw['name']}** requires **Tech {cw['required_tech']}**."),
                ephemeral=True
            )
            return

        # Cost
        cost = cw.get("cost", 0)
        if player["eddies"] < cost:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds", f"**{cw['name']}** costs **{cost:,} €$**. You have {player['eddies']:,} €$."),
                ephemeral=True
            )
            return

        # Check already installed
        installed = await self.db.get_cyberware(str(interaction.user.id))
        slot = cw.get("slot", "")
        if any(row["cyberware_id"] == cyberware_id for row in installed):
            await interaction.response.send_message(
                embed=error_embed("Already Installed", f"**{cw['name']}** is already installed."),
                ephemeral=True
            )
            return

        # Check humanity
        humanity_loss = cw.get("humanity_loss", 0)
        new_humanity = player.get("humanity", 100) - humanity_loss
        if new_humanity <= 0:
            await interaction.response.send_message(
                embed=error_embed(
                    "Cyberpsychosis Risk",
                    f"Installing **{cw['name']}** would reduce your humanity to **{new_humanity}**.\n"
                    f"You are at risk of cyberpsychosis. Remove other cyberware first."
                ),
                ephemeral=True
            )
            return

        # Remove existing in this slot (one slot can only hold one cyberware)
        existing_in_slot = next((row for row in installed if row["slot"] == slot), None)
        if existing_in_slot:
            old_cw = get_cyberware(existing_in_slot["cyberware_id"])
            await self.db.remove_cyberware(str(interaction.user.id), existing_in_slot["cyberware_id"])
            if old_cw:
                await self.db.reduce_humanity(str(interaction.user.id), -old_cw.get("humanity_loss", 0))  # Restore

        await self.db.add_eddies(str(interaction.user.id), -cost)
        await self.db.install_cyberware(str(interaction.user.id), cyberware_id, slot)
        await self.db.reduce_humanity(str(interaction.user.id), humanity_loss)

        rarity_emoji = get_rarity_emoji(cw.get("rarity", "common"))
        effects = cw.get("effects", {})
        effects_text = "\n".join(f"• +{v} {k.replace('_', ' ').title()}" for k, v in effects.items()) if effects else "No stat bonuses"

        embed = success_embed(
            "Cyberware Installed",
            f"{rarity_emoji} **{cw['name']}** installed in the **{SLOT_DISPLAY.get(slot, slot.title())}** slot.\n\n"
            f"**Effects:**\n{effects_text}\n\n"
            f"**Humanity:** {player.get('humanity',100)} → {new_humanity}\n"
            f"**Cost:** {cost:,} €$"
        )
        await interaction.response.send_message(embed=embed)

    # ── /cyberware remove ─────────────────────────────────────
    @app_commands.command(name="cwremove", description="Remove installed cyberware (partial humanity restore).")
    @app_commands.describe(cyberware_id="The cyberware ID to remove.")
    async def cwremove(self, interaction: discord.Interaction, cyberware_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        loc = get_location(player["location"])
        if not loc or "ripperdoc" not in loc.get("shops", []):
            await interaction.response.send_message(
                embed=error_embed("No Ripperdoc", "You need to be near a ripperdoc to remove cyberware."),
                ephemeral=True
            )
            return

        cyberware_id = cyberware_id.lower().replace(" ", "_")
        installed = await self.db.get_cyberware(str(interaction.user.id))
        installed_row = next((row for row in installed if row["cyberware_id"] == cyberware_id), None)

        if not installed_row:
            await interaction.response.send_message(
                embed=error_embed("Not Installed", f"You don't have `{cyberware_id}` installed."),
                ephemeral=True
            )
            return

        cw = get_cyberware(cyberware_id)
        name = cw["name"] if cw else cyberware_id
        removal_cost = int(cw.get("cost", 1000) * 0.25)  # 25% of install cost
        humanity_restore = int(cw.get("humanity_loss", 0) * 0.5)  # Restore 50%

        if player["eddies"] < removal_cost:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds", f"Removal costs **{removal_cost:,} €$**. You have {player['eddies']:,} €$."),
                ephemeral=True
            )
            return

        await self.db.remove_cyberware(str(interaction.user.id), cyberware_id)
        await self.db.add_eddies(str(interaction.user.id), -removal_cost)
        if humanity_restore > 0:
            await self.db.reduce_humanity(str(interaction.user.id), -humanity_restore)

        await interaction.response.send_message(
            embed=success_embed(
                "Cyberware Removed",
                f"**{name}** has been removed.\n\n"
                f"**Humanity restored:** +{humanity_restore}\n"
                f"**Removal fee:** {removal_cost:,} €$"
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CyberwareCog(bot))
