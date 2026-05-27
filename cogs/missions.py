"""
cogs/missions.py — Gigs, side jobs, main story missions, and bounties
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    mission_list_embed, mission_status_embed, error_embed, success_embed,
    info_embed, not_registered_embed
)
from utils.helpers import (
    get_mission, get_available_missions, get_item, format_eddies
)


class MissionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /jobs ─────────────────────────────────────────────────
    @app_commands.command(name="jobs", description="Browse available gigs and missions in Night City.")
    async def jobs(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        completed = await self.db.get_completed_mission_ids(str(interaction.user.id))
        active = await self.db.get_active_missions(str(interaction.user.id))
        active_ids = {m["mission_id"] for m in active}

        available = get_available_missions(player, completed)
        if not available:
            await interaction.response.send_message(
                embed=info_embed(
                    "No Jobs Available",
                    "There are no jobs available for your level/street cred right now.\n"
                    "Level up and gain more Street Cred to unlock more missions.",
                    config.COLORS["cyan"]
                ),
                ephemeral=True
            )
            return

        embed = mission_list_embed(available, active_ids, player)
        await interaction.response.send_message(embed=embed)

    # ── /job start ────────────────────────────────────────────
    job_group = app_commands.Group(name="job", description="Mission management commands.")

    @job_group.command(name="start", description="Start a mission or gig.")
    @app_commands.describe(mission_id="The mission ID to start (from /jobs list).")
    async def job_start(self, interaction: discord.Interaction, mission_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        mission_id = mission_id.lower().replace(" ", "_")
        mission = get_mission(mission_id)
        if not mission:
            await interaction.response.send_message(
                embed=error_embed("Unknown Mission", f"Mission `{mission_id}` not found. Use `/jobs` to see available missions."),
                ephemeral=True
            )
            return

        # Check if already active or completed
        active = await self.db.get_active_missions(str(interaction.user.id))
        if any(m["mission_id"] == mission_id for m in active):
            await interaction.response.send_message(
                embed=error_embed("Already Active", f"**{mission['name']}** is already in progress. Use `/job status` to check."),
                ephemeral=True
            )
            return

        completed = await self.db.get_completed_mission_ids(str(interaction.user.id))
        if mission_id in completed:
            await interaction.response.send_message(
                embed=error_embed("Already Completed", f"You've already completed **{mission['name']}**."),
                ephemeral=True
            )
            return

        # Check requirements
        req_level = mission.get("required_level", 1)
        req_cred = mission.get("required_street_cred", 0)
        req_missions = mission.get("required_missions", [])

        if player["level"] < req_level:
            await interaction.response.send_message(
                embed=error_embed("Level Too Low", f"**{mission['name']}** requires Level **{req_level}**. You are Level {player['level']}."),
                ephemeral=True
            )
            return
        if player["street_cred"] < req_cred:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Street Cred", f"**{mission['name']}** requires **{req_cred}** Street Cred."),
                ephemeral=True
            )
            return
        for req_m in req_missions:
            if req_m not in completed:
                req_mission = get_mission(req_m)
                req_name = req_mission["name"] if req_mission else req_m
                await interaction.response.send_message(
                    embed=error_embed("Prerequisite Missing", f"You must complete **{req_name}** before starting this mission."),
                    ephemeral=True
                )
                return

        # Check max concurrent active missions
        if len(active) >= config.MAX_ACTIVE_MISSIONS:
            await interaction.response.send_message(
                embed=error_embed("Too Many Active Jobs", f"You can only have {config.MAX_ACTIVE_MISSIONS} active jobs at once. Complete some first."),
                ephemeral=True
            )
            return

        await self.db.start_mission(str(interaction.user.id), mission_id)

        story = mission.get("story_text", {}).get("start", "")
        mission_type_emoji = {
            "gig": "📋", "side_job": "⭐", "main": "🔴", "bounty": "🎯"
        }.get(mission.get("type", "gig"), "📋")

        embed = discord.Embed(
            title=f"{mission_type_emoji} {mission['name']}",
            description=f"*{story}*" if story else "*A new job awaits.*",
            color=config.COLORS["yellow"]
        )
        embed.add_field(
            name="📝 First Objective",
            value=mission["objectives"][0]["text"] if mission.get("objectives") else "None",
            inline=False
        )
        embed.add_field(
            name="💰 Potential Rewards",
            value=(
                f"XP: {mission.get('rewards', {}).get('xp', 0):,}\n"
                f"Eddies: {mission.get('rewards', {}).get('eddies', 0):,} €$\n"
                f"Street Cred: +{mission.get('rewards', {}).get('street_cred', 0)}"
            ),
            inline=False
        )
        embed.set_footer(text="Use /job advance when you've completed the current objective.")
        await interaction.response.send_message(embed=embed)

    # ── /job status ───────────────────────────────────────────
    @job_group.command(name="status", description="Check the status of your active missions.")
    async def job_status(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        active = await self.db.get_active_missions(str(interaction.user.id))
        if not active:
            await interaction.response.send_message(
                embed=info_embed("No Active Jobs", "You have no active missions. Use `/jobs` to find new work.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        embed = mission_status_embed(active)
        await interaction.response.send_message(embed=embed)

    # ── /job advance ──────────────────────────────────────────
    @job_group.command(name="advance", description="Advance to the next objective in a mission.")
    @app_commands.describe(mission_id="The mission ID to advance (from /job status).")
    async def job_advance(self, interaction: discord.Interaction, mission_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        mission_id = mission_id.lower().replace(" ", "_")
        active = await self.db.get_active_missions(str(interaction.user.id))
        active_mission = next((m for m in active if m["mission_id"] == mission_id), None)

        if not active_mission:
            await interaction.response.send_message(
                embed=error_embed("Not Active", f"Mission `{mission_id}` is not currently active."),
                ephemeral=True
            )
            return

        mission_data = get_mission(mission_id)
        if not mission_data:
            await interaction.response.send_message(
                embed=error_embed("Data Error", "Could not load mission data."),
                ephemeral=True
            )
            return

        objectives = mission_data.get("objectives", [])
        current_step = active_mission["current_step"]

        if current_step >= len(objectives):
            await interaction.response.send_message(
                embed=error_embed("Already Complete", "This mission is already on its final step. Use `/job complete` to finish it."),
                ephemeral=True
            )
            return

        current_obj = objectives[current_step]
        obj_type = current_obj.get("type", "")

        # Auto-check travel objectives
        if obj_type == "travel":
            target_loc = current_obj.get("target", "")
            if player["location"] != target_loc:
                from utils.helpers import get_location
                target_loc_data = get_location(target_loc)
                target_name = target_loc_data["name"] if target_loc_data else target_loc.replace("_", " ").title()
                await interaction.response.send_message(
                    embed=info_embed(
                        "Objective: Travel",
                        f"You need to travel to **{target_name}**.\nUse `/travel` to get there.",
                        config.COLORS["yellow"]
                    ),
                    ephemeral=True
                )
                return

        new_step = current_step + 1
        if new_step >= len(objectives):
            # Complete the mission
            await self._complete_mission(interaction, player, mission_id, mission_data)
        else:
            await self.db.advance_mission(str(interaction.user.id), mission_id, new_step)
            next_obj = objectives[new_step]
            embed = discord.Embed(
                title=f"📋 Objective Updated: {mission_data['name']}",
                description=f"✅ Completed: *{current_obj['text']}*",
                color=config.COLORS["cyan"]
            )
            embed.add_field(name="📍 Next Objective", value=next_obj["text"], inline=False)
            await interaction.response.send_message(embed=embed)

    async def _complete_mission(self, interaction: discord.Interaction, player: dict, mission_id: str, mission_data: dict):
        rewards = mission_data.get("rewards", {})
        xp = rewards.get("xp", 100)
        eddies = rewards.get("eddies", 500)
        street_cred = rewards.get("street_cred", 1)
        faction_rep = rewards.get("faction_rep", {})
        item_rewards = rewards.get("items", [])

        await self.db.complete_mission(str(interaction.user.id), mission_id)
        level_result = await self.db.add_xp(str(interaction.user.id), xp)
        await self.db.add_eddies(str(interaction.user.id), eddies)
        await self.db.add_street_cred(str(interaction.user.id), street_cred)

        for faction, rep in faction_rep.items():
            await self.db.update_faction_rep(str(interaction.user.id), faction, rep)

        for item_id in item_rewards:
            await self.db.add_item(str(interaction.user.id), item_id, 1)

        story_end = mission_data.get("story_text", {}).get("complete", "")
        mission_type_emoji = {
            "gig": "📋", "side_job": "⭐", "main": "🔴", "bounty": "🎯"
        }.get(mission_data.get("type", "gig"), "📋")

        embed = discord.Embed(
            title=f"{mission_type_emoji} MISSION COMPLETE: {mission_data['name']}",
            description=f"*{story_end}*" if story_end else "*Job done.*",
            color=config.COLORS["green"]
        )
        reward_lines = [
            f"⭐ +**{xp:,} XP**",
            f"💰 +**{eddies:,} €$**",
            f"🏆 +**{street_cred}** Street Cred",
        ]
        for faction, rep in faction_rep.items():
            reward_lines.append(f"🤝 +**{rep}** {faction.replace('_', ' ').title()} rep")
        for item_id in item_rewards:
            itm = get_item(item_id)
            reward_lines.append(f"📦 {itm['icon'] if itm else '📦'} {itm['name'] if itm else item_id}")

        embed.add_field(name="🎁 Rewards", value="\n".join(reward_lines), inline=False)
        if level_result.get("leveled_up"):
            embed.add_field(name="🎉 LEVEL UP!", value=f"Now Level **{level_result['new_level']}**!", inline=False)

        await interaction.response.send_message(embed=embed)

    # ── /job complete (manual) ─────────────────────────────────
    @job_group.command(name="complete", description="Manually complete a mission if all objectives are done.")
    @app_commands.describe(mission_id="The mission ID to complete.")
    async def job_complete(self, interaction: discord.Interaction, mission_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        mission_id = mission_id.lower().replace(" ", "_")
        active = await self.db.get_active_missions(str(interaction.user.id))
        active_mission = next((m for m in active if m["mission_id"] == mission_id), None)

        if not active_mission:
            await interaction.response.send_message(
                embed=error_embed("Not Active", f"Mission `{mission_id}` is not currently active."),
                ephemeral=True
            )
            return

        mission_data = get_mission(mission_id)
        if not mission_data:
            await interaction.response.send_message(
                embed=error_embed("Data Error", "Could not load mission data."),
                ephemeral=True
            )
            return

        objectives = mission_data.get("objectives", [])
        if active_mission["current_step"] < len(objectives) - 1:
            await interaction.response.send_message(
                embed=error_embed("Not Finished", "You haven't completed all objectives yet. Use `/job advance` to progress."),
                ephemeral=True
            )
            return

        await self._complete_mission(interaction, player, mission_id, mission_data)

    # ── /job abandon ──────────────────────────────────────────
    @job_group.command(name="abandon", description="Abandon an active mission (no rewards).")
    @app_commands.describe(mission_id="The mission ID to abandon.")
    async def job_abandon(self, interaction: discord.Interaction, mission_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        mission_id = mission_id.lower().replace(" ", "_")
        active = await self.db.get_active_missions(str(interaction.user.id))
        if not any(m["mission_id"] == mission_id for m in active):
            await interaction.response.send_message(
                embed=error_embed("Not Active", f"Mission `{mission_id}` is not active."),
                ephemeral=True
            )
            return

        mission_data = get_mission(mission_id)
        name = mission_data["name"] if mission_data else mission_id

        await self.db.abandon_mission(str(interaction.user.id), mission_id)
        await interaction.response.send_message(
            embed=info_embed("Mission Abandoned", f"Abandoned **{name}**.\n*No rewards. You can restart it later.*", config.COLORS["yellow"])
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MissionsCog(bot))
