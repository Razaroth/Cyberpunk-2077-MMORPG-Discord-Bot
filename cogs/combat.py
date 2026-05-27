"""
cogs/combat.py — Turn-based combat system with Discord UI buttons
Handles both PvE (hunt) and PvP (duel) combat.
"""
from __future__ import annotations

import asyncio
import json
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    combat_embed, combat_victory_embed, combat_defeat_embed,
    error_embed, success_embed, info_embed, not_registered_embed
)
from utils.helpers import (
    calculate_player_stats, calculate_hit, calculate_flee_chance,
    roll_loot, pick_random_enemy_for_location, get_item, format_eddies, hp_bar, get_weapon_skill, get_cyberware
)


# ─────────────────────────────────────────────────────────────
#  Enemy AI
# ─────────────────────────────────────────────────────────────
def enemy_ai_attack(enemy: dict, skill_cooldowns: dict[str, int]) -> tuple[str, int, str]:
    """
    Returns (skill_used, damage, log_message).
    enemy is a scaled enemy dict. skill_cooldowns maps skill_name → turns_remaining.
    """
    from utils.helpers import load_data
    all_skills = load_data("enemies.json").get("enemy_skills", {})

    available_skills = [
        s for s in enemy.get("skills", [])
        if skill_cooldowns.get(s, 0) <= 0 and s in all_skills
    ]

    # 40% chance to use a skill if one is available
    chosen_skill = None
    if available_skills and random.random() < 0.40:
        chosen_skill = random.choice(available_skills)

    base_dmg = enemy.get("scaled_damage", enemy.get("base_damage", 30))
    armor = enemy.get("scaled_armor", enemy.get("base_armor", 5))

    if chosen_skill and chosen_skill in all_skills:
        skill_data = all_skills[chosen_skill]
        dmg_mult = skill_data.get("damage_mult", 1.0)
        flat_dmg = skill_data.get("flat_damage", 0)
        accuracy = skill_data.get("accuracy", 1.0)
        skill_emoji = skill_data.get("emoji", "⚡")

        if random.random() > accuracy:
            return chosen_skill, 0, f"{skill_emoji} **{skill_data['name']}** — missed!"

        raw = int(base_dmg * dmg_mult) + flat_dmg
        is_armor_ignore = skill_data.get("armor_ignore", False)
        if is_armor_ignore:
            dmg = max(1, raw)
        else:
            dmg = max(1, raw - armor // 2)

        return chosen_skill, dmg, f"{skill_emoji} **{skill_data['name']}** — {dmg} damage!"
    else:
        # Basic attack
        raw = base_dmg + random.randint(-5, 8)
        is_crit = random.random() < 0.08
        if is_crit:
            raw = int(raw * 1.5)
        dmg = max(1, raw - armor // 3)
        crit_txt = " **(CRIT!)**" if is_crit else ""
        return "basic", dmg, f"🗡️ Basic Attack{crit_txt} — {dmg} damage!"


# ─────────────────────────────────────────────────────────────
#  Combat View (buttons)
# ─────────────────────────────────────────────────────────────
class CombatView(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: str, player: dict, enemy: dict, enemy_id: str):
        super().__init__(timeout=config.COMBAT_TIMEOUT_SECONDS)
        self.bot = bot
        self.channel_id = channel_id
        self.player = player
        self.enemy = enemy
        self.enemy_id = enemy_id
        self.skill_cooldowns: dict[str, int] = {}
        self.combat_log: list[str] = []
        self.blood_pump_cooldown = 0
        self.dodge_active = False
        self.berserk_turns = 0

    async def _get_session(self):
        return await self.bot.db.get_combat_session(self.channel_id)

    async def _refresh_combat(self, interaction: discord.Interaction):
        session = await self._get_session()
        if not session:
            await interaction.message.delete()
            return None
        return session

    def _build_embed(self, session: dict) -> discord.Embed:
        extra = json.loads(session.get("extra_data", "{}"))
        enemy_name = extra.get("enemy_name", self.enemy.get("name", "Enemy"))
        enemy_emoji = extra.get("enemy_emoji", "👾")
        return combat_embed(
            self.player,
            session["player_hp"], session["player_max_hp"],
            enemy_name, session["opponent_hp"], session["opp_max_hp"],
            session["turn"], self.combat_log,
            enemy_emoji
        )

    def _tick_cooldowns(self):
        for k in list(self.skill_cooldowns.keys()):
            self.skill_cooldowns[k] = max(0, self.skill_cooldowns[k] - 1)
        self.blood_pump_cooldown = max(0, self.blood_pump_cooldown - 1)
        self.berserk_turns = max(0, self.berserk_turns - 1)

    async def _process_enemy_turn(self, session: dict) -> tuple[int, int]:
        """Returns (player_hp_after, enemy_hp_unchanged)."""
        player_hp = session["player_hp"]
        enemy_hp = session["opponent_hp"]
        skill_used, dmg, log_msg = enemy_ai_attack(self.enemy, self.skill_cooldowns)
        if skill_used != "basic" and skill_used in (self.enemy.get("skills", [])):
            from utils.helpers import load_data
            skill_data = load_data("enemies.json").get("enemy_skills", {}).get(skill_used, {})
            cd = skill_data.get("cooldown_turns", 3)
            self.skill_cooldowns[skill_used] = cd

        # Dodge reduces damage
        if self.dodge_active and dmg > 0:
            roll = random.random()
            equipped = await self.bot.db.get_equipped_items(str(self.player["user_id"]))
            stats = calculate_player_stats(self.player, equipped)
            dodge_chance = stats["dodge_chance"]
            if roll < dodge_chance:
                self.combat_log.append(f"💨 **{self.player['username']}** dodged the attack!")
                self.dodge_active = False
                return player_hp, enemy_hp
            self.dodge_active = False

        # Cyberware passive: subdermal armor reduces damage
        cyberware = await self.bot.db.get_cyberware(str(self.player["user_id"]))
        cw_armor = 0
        for row in cyberware:
            cw_item = get_cyberware(row["cyberware_id"])
            if cw_item:
                cw_armor += cw_item.get("armor", 0)
        dmg = max(1, dmg - cw_armor // 4)

        player_hp = max(0, player_hp - dmg)
        self.combat_log.append(f"👾 {log_msg}")
        return player_hp, enemy_hp

    async def _end_combat_victory(self, interaction: discord.Interaction, session: dict):
        await self.bot.db.end_combat(self.channel_id, "victory")
        extra = json.loads(session.get("extra_data", "{}"))
        enemy_name = extra.get("enemy_name", "Enemy")
        xp = self.enemy.get("scaled_xp", self.enemy.get("xp_reward", 60))
        eddies = self.enemy.get("scaled_eddies", random.randint(50, 200))
        loot = roll_loot(self.enemy, self.player["level"])

        level_result = await self.bot.db.add_xp(str(self.player["user_id"]), xp)
        await self.bot.db.add_eddies(str(self.player["user_id"]), eddies)
        await self.bot.db.add_street_cred(str(self.player["user_id"]), 1)
        await self.bot.db.full_heal(str(self.player["user_id"]))

        # Add loot to inventory
        for item_id in loot:
            await self.bot.db.add_item(str(self.player["user_id"]), item_id, 1)

        # Skill XP
        equipped = await self.bot.db.get_equipped_items(str(self.player["user_id"]))
        weapon_id = equipped.get("weapon")
        if weapon_id:
            weapon = get_item(weapon_id)
            if weapon:
                skill_name = get_weapon_skill(weapon.get("weapon_type", ""))
                await self.bot.db.add_skill_xp(str(self.player["user_id"]), skill_name, 25)

        updated_player = await self.bot.db.get_player(str(self.player["user_id"]))
        embed = combat_victory_embed(updated_player, enemy_name, xp, eddies, loot)
        if level_result.get("leveled_up"):
            embed.add_field(
                name="🎉 LEVEL UP!",
                value=f"You are now **Level {level_result['new_level']}**!\nUse `/levelup` to spend attribute points.",
                inline=False
            )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    async def _end_combat_defeat(self, interaction: discord.Interaction, session: dict):
        await self.bot.db.end_combat(self.channel_id, "defeat")
        extra = json.loads(session.get("extra_data", "{}"))
        enemy_name = extra.get("enemy_name", "Enemy")
        # Penalize 10% of eddies
        player = await self.bot.db.get_player(str(self.player["user_id"]))
        penalty = int(player["eddies"] * 0.10)
        await self.bot.db.add_eddies(str(self.player["user_id"]), -penalty)
        await self.bot.db.update_player(str(self.player["user_id"]), health=max(1, player["max_health"] // 4))
        embed = combat_defeat_embed(player, enemy_name)
        embed.add_field(name="💸 Medical Fees", value=f"Lost **{penalty:,} €$**", inline=True)
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    # ── Attack Button ──────────────────────────────────────────
    @discord.ui.button(label="⚔️ Attack", style=discord.ButtonStyle.danger, row=0)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self._refresh_combat(interaction)
        if not session:
            return
        if str(interaction.user.id) != session["player_id"]:
            await interaction.response.send_message("This isn't your fight!", ephemeral=True)
            return
        if not session["player_turn"]:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return

        equipped = await self.bot.db.get_equipped_items(str(interaction.user.id))
        stats = calculate_player_stats(self.player, equipped)

        # Berserk boost
        if self.berserk_turns > 0:
            stats["damage"] = int(stats["damage"] * 1.4)

        dmg, is_crit = calculate_hit(stats["damage"], 0, stats["crit_chance"])
        crit_txt = " **(CRIT!)**" if is_crit else ""
        self.combat_log.append(f"⚔️ {self.player['username']} attacks for **{dmg}** damage{crit_txt}!")

        # Apply damage to enemy
        new_enemy_hp = max(0, session["opponent_hp"] - dmg)

        # Add skill XP for attack
        weapon_id = equipped.get("weapon")
        if weapon_id:
            weapon = get_item(weapon_id)
            if weapon:
                skill_name = get_weapon_skill(weapon.get("weapon_type", ""))
                await self.bot.db.add_skill_xp(str(interaction.user.id), skill_name, 8)

        if new_enemy_hp <= 0:
            await self.bot.db.update_combat(self.channel_id, opponent_hp=0)
            await self._end_combat_victory(interaction, session)
            return

        # Enemy turn
        updated_session = {**session, "opponent_hp": new_enemy_hp}
        self._tick_cooldowns()
        player_hp, _ = await self._process_enemy_turn(updated_session)

        turn = session["turn"] + 1
        await self.bot.db.update_combat(
            self.channel_id,
            opponent_hp=new_enemy_hp,
            player_hp=player_hp,
            turn=turn
        )

        if player_hp <= 0:
            updated_session["player_hp"] = 0
            await self._end_combat_defeat(interaction, updated_session)
            return

        updated_session["player_hp"] = player_hp
        updated_session["opponent_hp"] = new_enemy_hp
        updated_session["turn"] = turn
        embed = self._build_embed(updated_session)
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Dodge Button ───────────────────────────────────────────
    @discord.ui.button(label="💨 Dodge", style=discord.ButtonStyle.primary, row=0)
    async def dodge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self._refresh_combat(interaction)
        if not session:
            return
        if str(interaction.user.id) != session["player_id"]:
            await interaction.response.send_message("This isn't your fight!", ephemeral=True)
            return

        self.dodge_active = True
        self.combat_log.append(f"💨 {self.player['username']} prepares to dodge the next attack!")
        self._tick_cooldowns()
        player_hp, _ = await self._process_enemy_turn(session)
        turn = session["turn"] + 1
        await self.bot.db.update_combat(self.channel_id, player_hp=player_hp, turn=turn)

        if player_hp <= 0:
            await self._end_combat_defeat(interaction, {**session, "player_hp": 0})
            return

        updated = {**session, "player_hp": player_hp, "turn": turn}
        embed = self._build_embed(updated)
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Quick Hack Button ──────────────────────────────────────
    @discord.ui.button(label="💻 Quick Hack", style=discord.ButtonStyle.secondary, row=0)
    async def quickhack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self._refresh_combat(interaction)
        if not session:
            return
        if str(interaction.user.id) != session["player_id"]:
            await interaction.response.send_message("This isn't your fight!", ephemeral=True)
            return

        # Check if player has a cyberdeck
        cyberware = await self.bot.db.get_cyberware(str(interaction.user.id))
        has_deck = any(row["slot"] == "operating_system" and "cyberdeck" in row["cyberware_id"] for row in cyberware)
        if not has_deck:
            await interaction.response.send_message(
                embed=error_embed("No Cyberdeck", "You need an Operating System cyberware (Cyberdeck) to use Quick Hacks.\nVisit a Ripperdoc with `/ripperdoc`."),
                ephemeral=True
            )
            return

        player = await self.bot.db.get_player(str(interaction.user.id))
        # Quickhack damage based on Intelligence
        hack_damage = 20 + player["intelligence"] * 8
        # Random hack effect
        hacks = [
            ("⚡ Short Circuit", hack_damage, "electrical"),
            ("🦠 Contagion", hack_damage // 2, "dot"),
            ("💥 Overheat", int(hack_damage * 1.3), "thermal"),
            ("🧠 Synapse Burnout", hack_damage, "neural"),
        ]
        hack_name, dmg, _ = random.choice(hacks)
        self.combat_log.append(f"{hack_name} — {dmg} damage to {self.enemy.get('name', 'Enemy')}!")

        new_enemy_hp = max(0, session["opponent_hp"] - dmg)
        if new_enemy_hp <= 0:
            await self.bot.db.update_combat(self.channel_id, opponent_hp=0)
            await self._end_combat_victory(interaction, session)
            return

        self._tick_cooldowns()
        player_hp, _ = await self._process_enemy_turn({**session, "opponent_hp": new_enemy_hp})
        turn = session["turn"] + 1

        await self.bot.db.update_combat(
            self.channel_id, opponent_hp=new_enemy_hp, player_hp=player_hp, turn=turn
        )
        if player_hp <= 0:
            await self._end_combat_defeat(interaction, {**session, "player_hp": 0})
            return

        updated = {**session, "player_hp": player_hp, "opponent_hp": new_enemy_hp, "turn": turn}
        embed = self._build_embed(updated)
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Use Item Button ────────────────────────────────────────
    @discord.ui.button(label="💊 Use Item", style=discord.ButtonStyle.success, row=1)
    async def use_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self._refresh_combat(interaction)
        if not session:
            return
        if str(interaction.user.id) != session["player_id"]:
            await interaction.response.send_message("This isn't your fight!", ephemeral=True)
            return

        # Try healing items in order
        heal_items = [
            ("maxdoc_mk3", 150), ("bounceback_mk3", 120),
            ("maxdoc_mk2", 80), ("bounceback_mk1", 30), ("maxdoc_mk1", 40),
        ]
        used = False
        for item_id, heal_amt in heal_items:
            inv = await self.bot.db.get_inventory_item(str(interaction.user.id), item_id)
            if inv and inv["quantity"] > 0:
                await self.bot.db.remove_item(str(interaction.user.id), item_id, 1)
                new_hp = min(session["player_max_hp"], session["player_hp"] + heal_amt)
                item = get_item(item_id)
                self.combat_log.append(f"💊 Used **{item['name'] if item else item_id}** — healed {heal_amt} HP!")
                await self.bot.db.update_combat(self.channel_id, player_hp=new_hp)
                self._tick_cooldowns()
                # Enemy still attacks this turn
                player_hp, _ = await self._process_enemy_turn({**session, "player_hp": new_hp})
                turn = session["turn"] + 1
                await self.bot.db.update_combat(self.channel_id, player_hp=player_hp, turn=turn)
                if player_hp <= 0:
                    await self._end_combat_defeat(interaction, {**session, "player_hp": 0})
                    return
                updated = {**session, "player_hp": player_hp, "turn": turn}
                embed = self._build_embed(updated)
                await interaction.response.edit_message(embed=embed, view=self)
                used = True
                break

        if not used:
            await interaction.response.send_message(
                embed=error_embed("No Healing Items", "You don't have any healing items! You're on your own."),
                ephemeral=True
            )

    # ── Flee Button ────────────────────────────────────────────
    @discord.ui.button(label="🏃 Flee", style=discord.ButtonStyle.secondary, row=1)
    async def flee_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self._refresh_combat(interaction)
        if not session:
            return
        if str(interaction.user.id) != session["player_id"]:
            await interaction.response.send_message("This isn't your fight!", ephemeral=True)
            return

        flee_chance = calculate_flee_chance(self.player)
        if random.random() < flee_chance:
            await self.bot.db.end_combat(self.channel_id, "fled")
            self.stop()
            await interaction.response.edit_message(
                embed=info_embed(
                    "Escaped!",
                    f"*You slip away into the shadows. The enemy lets you go — this time.*\n"
                    f"No rewards, but you live to fight another day.",
                    config.COLORS["cyan"]
                ),
                view=None
            )
        else:
            self.combat_log.append(f"🏃 Flee attempt failed! The enemy blocks your escape!")
            self._tick_cooldowns()
            player_hp, _ = await self._process_enemy_turn(session)
            turn = session["turn"] + 1
            await self.bot.db.update_combat(self.channel_id, player_hp=player_hp, turn=turn)
            if player_hp <= 0:
                await self._end_combat_defeat(interaction, {**session, "player_hp": 0})
                return
            updated = {**session, "player_hp": player_hp, "turn": turn}
            embed = self._build_embed(updated)
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        try:
            await self.bot.db.end_combat(self.channel_id, "timeout")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  The Cog
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    @app_commands.command(name="hunt", description="Hunt enemies in your current location for XP and loot.")
    async def hunt(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        if player["health"] <= 0:
            await interaction.response.send_message(
                embed=error_embed("Flatlined", "You're critically injured. Use `/heal` before fighting again."),
                ephemeral=True
            )
            return

        # Check for active combat
        existing = await self.db.get_player_combat(str(interaction.user.id))
        if existing:
            await interaction.response.send_message(
                embed=error_embed("Already in Combat", "You're already in combat! Finish the current fight first."),
                ephemeral=True
            )
            return

        # Check existing combat in this channel
        chan_existing = await self.db.get_combat_session(str(interaction.channel.id))
        if chan_existing:
            await interaction.response.send_message(
                embed=error_embed("Channel Busy", "There's already a combat happening in this channel. Use another channel."),
                ephemeral=True
            )
            return

        enemy_id, enemy = pick_random_enemy_for_location(player["location"], player["level"])
        equipped = await self.db.get_equipped_items(str(interaction.user.id))
        player_stats = calculate_player_stats(player, equipped)

        await self.db.create_combat_session(
            channel_id=str(interaction.channel.id),
            player_id=str(interaction.user.id),
            opponent_type="pve",
            opponent_id=enemy_id,
            player_hp=player["health"],
            opponent_hp=enemy["scaled_hp"],
            extra_data={
                "enemy_name": enemy["name"],
                "enemy_emoji": enemy.get("emoji", "👾"),
                "enemy_faction": enemy.get("faction", ""),
            }
        )

        view = CombatView(self.bot, str(interaction.channel.id), player, enemy, enemy_id)

        # Random enemy dialogue
        dialogue = random.choice(enemy.get("dialogue", ["..."]))

        embed = discord.Embed(
            title=f"⚔️ COMBAT INITIATED",
            description=(
                f"A **{enemy['name']}** ({enemy.get('emoji','👾')}) appears!\n\n"
                f"*\"{dialogue}\"*\n\n"
                f"**{enemy['name']}** — {enemy.get('description','')[:100]}"
            ),
            color=config.COLORS["red"]
        )
        embed.add_field(name=f"❤️ {player['username']}", value=hp_bar(player["health"], player["max_health"], 10), inline=True)
        embed.add_field(name=f"{enemy.get('emoji','👾')} {enemy['name']}", value=hp_bar(enemy["scaled_hp"], enemy["scaled_hp"], 10), inline=True)
        embed.set_footer(text="Choose your action!")

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="duel", description="Challenge another player to a PvP duel.")
    @app_commands.describe(target="The player you want to challenge.")
    async def duel(self, interaction: discord.Interaction, target: discord.Member):
        if target.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Invalid Target", "You can't duel yourself."),
                ephemeral=True
            )
            return
        if target.bot:
            await interaction.response.send_message(
                embed=error_embed("Invalid Target", "You can't duel a bot."),
                ephemeral=True
            )
            return

        challenger = await self.db.get_player(str(interaction.user.id))
        if not challenger:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        defender = await self.db.get_player(str(target.id))
        if not defender:
            await interaction.response.send_message(
                embed=error_embed("Target Not Registered", f"{target.display_name} doesn't have a character."),
                ephemeral=True
            )
            return

        # Duel accept view
        class DuelAcceptView(discord.ui.View):
            def __init__(self, challenger_id: str, defender_id: str):
                super().__init__(timeout=60)
                self.challenger_id = challenger_id
                self.defender_id = defender_id
                self.accepted = False

            @discord.ui.button(label="⚔️ Accept Duel", style=discord.ButtonStyle.danger)
            async def accept(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if str(btn_interaction.user.id) != self.defender_id:
                    await btn_interaction.response.send_message("Only the challenged player can accept!", ephemeral=True)
                    return
                self.accepted = True
                self.stop()
                await btn_interaction.response.defer()

            @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.secondary)
            async def decline(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if str(btn_interaction.user.id) not in (self.defender_id, self.challenger_id):
                    await btn_interaction.response.send_message("You're not involved in this duel!", ephemeral=True)
                    return
                self.stop()
                await btn_interaction.response.edit_message(
                    embed=info_embed("Duel Declined", f"{target.display_name} declined the challenge."),
                    view=None
                )

        duel_view = DuelAcceptView(str(interaction.user.id), str(target.id))
        embed = discord.Embed(
            title="⚔️ DUEL CHALLENGE",
            description=(
                f"**{interaction.user.display_name}** (Lv.{challenger['level']}) "
                f"challenges **{target.display_name}** (Lv.{defender['level']}) to a duel!\n\n"
                f"{target.mention}, do you accept?"
            ),
            color=config.COLORS["yellow"]
        )
        await interaction.response.send_message(embed=embed, view=duel_view)
        await duel_view.wait()

        if not duel_view.accepted:
            return

        # Start PvP combat (challenger goes first)
        equipped_c = await self.db.get_equipped_items(str(interaction.user.id))
        equipped_d = await self.db.get_equipped_items(str(target.id))
        stats_c = calculate_player_stats(challenger, equipped_c)
        stats_d = calculate_player_stats(defender, equipped_d)

        # Simple PvP resolution (alternating rounds)
        c_hp = challenger["health"]
        d_hp = defender["health"]
        log = []
        rounds = 0
        max_rounds = 20

        while c_hp > 0 and d_hp > 0 and rounds < max_rounds:
            # Challenger attacks
            dmg, crit = calculate_hit(stats_c["damage"], stats_d["armor"] // 2, stats_c["crit_chance"])
            d_hp = max(0, d_hp - dmg)
            log.append(f"⚔️ {challenger['username']} deals **{dmg}**{'**(CRIT)**' if crit else ''} to {defender['username']}")
            if d_hp <= 0:
                break
            # Defender attacks
            dmg2, crit2 = calculate_hit(stats_d["damage"], stats_c["armor"] // 2, stats_d["crit_chance"])
            c_hp = max(0, c_hp - dmg2)
            log.append(f"⚔️ {defender['username']} deals **{dmg2}**{'**(CRIT)**' if crit2 else ''} to {challenger['username']}")
            rounds += 1

        if c_hp <= 0 and d_hp <= 0:
            winner_id, loser_id, winner, loser = None, None, None, None
            result_text = "🤝 It's a draw! Both fighters are down."
        elif d_hp <= 0:
            winner, loser = challenger, defender
            winner_id, loser_id = str(interaction.user.id), str(target.id)
            result_text = f"🏆 **{challenger['username']}** wins the duel!"
        else:
            winner, loser = defender, challenger
            winner_id, loser_id = str(target.id), str(interaction.user.id)
            result_text = f"🏆 **{defender['username']}** wins the duel!"

        result_embed = discord.Embed(
            title="⚔️ DUEL COMPLETE",
            description=result_text,
            color=config.COLORS["yellow"]
        )
        result_embed.add_field(name="📜 Combat Summary", value="\n".join(log[-6:]) if log else "No log", inline=False)

        if winner_id:
            prize = min(500, int(loser["eddies"] * 0.05))
            await self.db.add_eddies(winner_id, prize + 200)
            xp_won = 200 + (loser["level"] - winner["level"]) * 50
            await self.db.add_xp(winner_id, max(100, xp_won))
            await self.db.add_street_cred(winner_id, 3)
            # Collect bounties if any
            bounty = await self.db.collect_bounty(loser_id, winner_id)
            if bounty > 0:
                result_embed.add_field(name="🎯 Bounty Collected!", value=f"+**{bounty:,} €$** from active bounties!", inline=False)
            result_embed.add_field(
                name="🏆 Winner Rewards",
                value=f"+**{prize + 200:,} €$** | +**{max(100, xp_won)} XP** | +3 Street Cred",
                inline=False
            )

        await interaction.edit_original_response(embed=result_embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))
