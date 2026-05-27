"""
cogs/skills.py — Skill progression and perk tree
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    skills_embed, error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import get_perk, get_rarity_emoji


class SkillsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /skills ───────────────────────────────────────────────
    @app_commands.command(name="skills", description="View your skills, levels, and available perk points.")
    async def skills_view(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        skill_data = await self.db.get_skills(str(interaction.user.id))
        embed = skills_embed(player, skill_data)
        await interaction.response.send_message(embed=embed)

    # ── /perks ────────────────────────────────────────────────
    @app_commands.command(name="perks", description="Browse the perk tree and see what you can unlock.")
    @app_commands.describe(attribute="Filter perks by attribute (optional).")
    @app_commands.choices(attribute=[
        app_commands.Choice(name="Body", value="body"),
        app_commands.Choice(name="Reflexes", value="reflexes"),
        app_commands.Choice(name="Tech", value="tech"),
        app_commands.Choice(name="Intelligence", value="intelligence"),
        app_commands.Choice(name="Cool", value="cool"),
    ])
    async def perks_view(self, interaction: discord.Interaction, attribute: app_commands.Choice[str] = None):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        from utils.helpers import load_data
        perk_tree = load_data("perks.json")
        unlocked = await self.db.get_perks(str(interaction.user.id))
        unlocked_ids = {p["perk_id"] for p in unlocked}
        skill_data = await self.db.get_skills(str(interaction.user.id))
        skill_levels = {s["skill_id"]: s["level"] for s in skill_data}

        perk_points = player.get("perk_points", 0)

        embed = discord.Embed(
            title="🔧 PERK TREE",
            description=f"**Available Perk Points:** {perk_points}\nUse `/perk unlock <perk_id>` to unlock a perk.",
            color=config.COLORS["yellow"]
        )

        filter_attr = attribute.value if attribute else None

        for attr_key, attr_perks in perk_tree.items():
            if filter_attr and attr_key != filter_attr:
                continue
            attr_info = config.ATTRIBUTES.get(attr_key, {})
            attr_emoji = attr_info.get("emoji", "⭐")
            attr_name = attr_info.get("name", attr_key.title())

            lines = []
            if isinstance(attr_perks, dict):
                for skill_key, skill_perks in attr_perks.items():
                    if not isinstance(skill_perks, dict):
                        continue
                    skill_lvl = skill_levels.get(skill_key, 0)
                    for perk_id, perk_data in skill_perks.items():
                        if not isinstance(perk_data, dict):
                            continue
                        req_skill_lvl = perk_data.get("required_skill_level", 0)
                        is_unlocked = perk_id in unlocked_ids
                        can_unlock = (
                            not is_unlocked
                            and skill_lvl >= req_skill_lvl
                            and perk_points >= perk_data.get("cost", 1)
                        )
                        if is_unlocked:
                            prefix = "✅"
                        elif can_unlock:
                            prefix = "🟡"
                        else:
                            prefix = "🔒"

                        cost = perk_data.get("cost", 1)
                        req_txt = f"(Skill Lv.{req_skill_lvl})" if req_skill_lvl > 0 else ""
                        lines.append(f"{prefix} **{perk_data['name']}** {req_txt} — {cost} pt{'s' if cost != 1 else ''} | `{perk_id}`")

            if lines:
                embed.add_field(
                    name=f"{attr_emoji} {attr_name}",
                    value="\n".join(lines[:8]),
                    inline=False
                )

        embed.set_footer(text="✅ Unlocked | 🟡 Available | 🔒 Locked")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /perk unlock ──────────────────────────────────────────
    perk_group = app_commands.Group(name="perk", description="Perk management commands.")

    @perk_group.command(name="unlock", description="Spend a perk point to unlock a perk.")
    @app_commands.describe(perk_id="The perk ID to unlock (from /perks list).")
    async def perk_unlock(self, interaction: discord.Interaction, perk_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        perk_id = perk_id.lower().replace(" ", "_")
        perk_data = get_perk(perk_id)
        if not perk_data:
            await interaction.response.send_message(
                embed=error_embed("Unknown Perk", f"Perk `{perk_id}` not found. Use `/perks` to see available perks."),
                ephemeral=True
            )
            return

        # Already unlocked?
        if await self.db.has_perk(str(interaction.user.id), perk_id):
            await interaction.response.send_message(
                embed=error_embed("Already Unlocked", f"You've already unlocked **{perk_data['name']}**."),
                ephemeral=True
            )
            return

        perk_cost = perk_data.get("cost", 1)
        perk_points = player.get("perk_points", 0)
        if perk_points < perk_cost:
            await interaction.response.send_message(
                embed=error_embed(
                    "Not Enough Perk Points",
                    f"**{perk_data['name']}** costs **{perk_cost}** perk point(s). You have {perk_points}.\n"
                    f"Gain perk points by leveling up skills."
                ),
                ephemeral=True
            )
            return

        # Skill level requirement
        req_skill_level = perk_data.get("required_skill_level", 0)
        req_skill = perk_data.get("skill", "")
        if req_skill and req_skill_level > 0:
            skills = await self.db.get_skills(str(interaction.user.id))
            skill_row = next((s for s in skills if s["skill_id"] == req_skill), None)
            current_skill_lvl = skill_row["level"] if skill_row else 0
            if current_skill_lvl < req_skill_level:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Skill Level Too Low",
                        f"**{perk_data['name']}** requires **{req_skill.replace('_',' ').title()} Level {req_skill_level}**.\n"
                        f"You are at {current_skill_lvl}."
                    ),
                    ephemeral=True
                )
                return

        # Prerequisite perks
        req_perks = perk_data.get("required_perks", [])
        for req_p in req_perks:
            if not await self.db.has_perk(str(interaction.user.id), req_p):
                req_perk_data = get_perk(req_p)
                req_name = req_perk_data["name"] if req_perk_data else req_p
                await interaction.response.send_message(
                    embed=error_embed("Prerequisite Missing", f"You must unlock **{req_name}** first."),
                    ephemeral=True
                )
                return

        await self.db.unlock_perk(str(interaction.user.id), perk_id)
        await self.db.update_player(str(interaction.user.id), perk_points=perk_points - perk_cost)

        effects = perk_data.get("effects", {})
        effects_text = "\n".join(f"• {v}" for v in effects.values()) if effects else perk_data.get("description", "No description")

        embed = success_embed(
            "Perk Unlocked!",
            f"🔧 **{perk_data['name']}** has been unlocked!\n\n"
            f"**Effect:**\n{effects_text}\n\n"
            f"Remaining perk points: {perk_points - perk_cost}"
        )
        await interaction.response.send_message(embed=embed)

    # ── /skillup ──────────────────────────────────────────────
    @app_commands.command(name="skillup", description="Upgrade a skill using skill points (earned from combat/missions).")
    @app_commands.describe(skill="The skill to upgrade.")
    @app_commands.choices(skill=[
        app_commands.Choice(name="Athletics", value="athletics"),
        app_commands.Choice(name="Annihilation", value="annihilation"),
        app_commands.Choice(name="Street Brawler", value="street_brawler"),
        app_commands.Choice(name="Assault", value="assault"),
        app_commands.Choice(name="Handguns", value="handguns"),
        app_commands.Choice(name="Blades", value="blades"),
        app_commands.Choice(name="Crafting", value="crafting"),
        app_commands.Choice(name="Engineering", value="engineering"),
        app_commands.Choice(name="Breach Protocol", value="breach_protocol"),
        app_commands.Choice(name="Quickhacking", value="quickhacking"),
        app_commands.Choice(name="Cold Blood", value="cold_blood"),
        app_commands.Choice(name="Stealth", value="stealth"),
        app_commands.Choice(name="Ninjutsu", value="ninjutsu"),
    ])
    async def skillup(self, interaction: discord.Interaction, skill: app_commands.Choice[str]):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        skill_points = player.get("skill_points", 0)
        if skill_points < 1:
            await interaction.response.send_message(
                embed=error_embed(
                    "No Skill Points",
                    "You don't have any skill points.\n"
                    "Earn skill points by using skills in combat, completing missions, and gaining levels."
                ),
                ephemeral=True
            )
            return

        skills = await self.db.get_skills(str(interaction.user.id))
        skill_row = next((s for s in skills if s["skill_id"] == skill.value), None)
        current_level = skill_row["level"] if skill_row else 1
        max_skill_level = config.MAX_SKILL_LEVEL

        if current_level >= max_skill_level:
            await interaction.response.send_message(
                embed=error_embed("Max Level", f"**{skill.name}** is already at maximum level ({max_skill_level})."),
                ephemeral=True
            )
            return

        # Cost scales with current level
        cost = max(1, current_level // 5 + 1)
        if skill_points < cost:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Points", f"Upgrading **{skill.name}** to level {current_level+1} costs **{cost}** skill points. You have {skill_points}."),
                ephemeral=True
            )
            return

        # Add a large XP chunk to trigger level up
        await self.db.add_skill_xp(str(interaction.user.id), skill.value, 9999)
        await self.db.update_player(str(interaction.user.id), skill_points=skill_points - cost)

        # Perk point at every 5 skill levels
        new_level = current_level + 1
        if new_level % 5 == 0:
            perk_pts = player.get("perk_points", 0)
            await self.db.update_player(str(interaction.user.id), perk_points=perk_pts + 1)
            perk_bonus = "\n🎁 **+1 Perk Point** earned!"
        else:
            perk_bonus = ""

        embed = success_embed(
            "Skill Upgraded!",
            f"**{skill.name}** upgraded to Level **{new_level}**!\n"
            f"Skill points used: {cost} | Remaining: {skill_points - cost}"
            f"{perk_bonus}"
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SkillsCog(bot))
