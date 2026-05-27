"""
utils/embeds.py — Cyberpunk-themed Discord embed builders for Night City MMORPG
"""
from __future__ import annotations

import discord
from datetime import datetime, timezone
from typing import Optional

import config
from utils.helpers import (
    make_progress_bar, hp_bar, format_eddies, format_number,
    xp_to_next, level_progress_pct, get_rarity_color, get_rarity_emoji,
    get_item, get_cyberware, get_location
)


FOOTER_ICON = None  # Set to a URL if you have a bot icon

def _footer(text: str = "NIGHT CITY ONLINE") -> discord.EmbedFooter:
    return discord.EmbedFooter(text=f"⚡ {text} ⚡")


# ─────────────────────────────────────────────────────────────
#  Profile & Character
# ─────────────────────────────────────────────────────────────
def profile_embed(player: dict, user: discord.User, equipped: dict, faction_rep: dict) -> discord.Embed:
    lifepath_info = config.LIFEPATHS.get(player["lifepath"], {})
    lp_emoji = lifepath_info.get("emoji", "")
    location = get_location(player["location"])
    loc_name = location["name"] if location else player["location"]

    xp_pct = level_progress_pct(player)
    xp_bar = make_progress_bar(xp_pct, 12)
    hp_display = hp_bar(player["health"], player["max_health"], 10)
    humanity_pct = (player["humanity"] / player["max_humanity"]) * 100 if player["max_humanity"] > 0 else 0
    hum_bar = make_progress_bar(humanity_pct, 10)

    # Street cred title
    title = config.get_street_cred_title(player["street_cred"])

    # Top faction by rep
    top_faction = max(faction_rep.items(), key=lambda x: x[1], default=(None, 0))
    faction_display = ""
    if top_faction[0] and top_faction[1] > 0:
        finfo = config.FACTIONS.get(top_faction[0], {})
        faction_display = f"{finfo.get('emoji','')} {finfo.get('name', top_faction[0])} (+{top_faction[1]})"

    embed = discord.Embed(
        title=f"╔══ {lp_emoji} {player['username'].upper()} ══╗",
        description=(
            f"**Class:** {lifepath_info.get('name', player['lifepath'])}\n"
            f"**Street Cred:** {player['street_cred']} — *{title}*\n"
            f"**Location:** {loc_name}\n"
            f"{('**Affiliation:** ' + faction_display) if faction_display else ''}"
        ),
        color=config.COLORS["yellow"]
    )

    embed.add_field(
        name="📊 Level & XP",
        value=(
            f"**Level {player['level']}** / {config.MAX_LEVEL}\n"
            f"`{xp_bar}` {xp_pct:.1f}%\n"
            f"{format_number(player['xp'])} XP | {format_number(xp_to_next(player))} to next"
        ),
        inline=False
    )
    embed.add_field(
        name="❤️ Health",
        value=f"`{hp_display}`",
        inline=True
    )
    embed.add_field(
        name="🧬 Humanity",
        value=f"`{hum_bar}` {player['humanity']}/{player['max_humanity']}",
        inline=True
    )
    embed.add_field(
        name="💰 Eddies",
        value=f"**{player['eddies']:,} €$**",
        inline=True
    )
    embed.add_field(
        name="⚡ Attributes",
        value=(
            f"💪 **Body** {player['body']}  "
            f"⚡ **Reflex** {player['reflexes']}\n"
            f"🔧 **Tech** {player['tech']}  "
            f"🧠 **Intel** {player['intelligence']}\n"
            f"😎 **Cool** {player['cool']}"
        ),
        inline=False
    )

    # Equipped gear
    gear_lines = []
    slots = {"weapon": "🔫 Weapon", "head": "🪖 Head", "torso": "🧥 Torso", "arms": "🥊 Arms", "legs": "👖 Legs"}
    for slot_key, slot_name in slots.items():
        item_id = equipped.get(slot_key)
        if item_id:
            item = get_item(item_id)
            if item:
                gear_lines.append(f"**{slot_name}:** {item['name']}")
            else:
                gear_lines.append(f"**{slot_name}:** {item_id}")
        else:
            gear_lines.append(f"**{slot_name}:** *Empty*")
    embed.add_field(name="🛡️ Equipped Gear", value="\n".join(gear_lines), inline=False)

    if player.get("attr_points", 0) > 0 or player.get("skill_points", 0) > 0:
        embed.add_field(
            name="⬆️ Unspent Points",
            value=(
                f"Attribute: **{player['attr_points']}**  "
                f"Skill: **{player['skill_points']}**  "
                f"Perk: **{player['perk_points']}**\n"
                f"Use `/levelup` and `/skills upgrade` to spend them!"
            ),
            inline=False
        )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="⚡ NIGHT CITY ONLINE  •  /help for commands")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def stats_embed(player: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {player['username']}'s Attribute Stats",
        color=config.COLORS["cyan"]
    )
    for attr_key, attr_info in config.ATTRIBUTES.items():
        val = player[attr_key]
        bar = make_progress_bar((val / config.MAX_ATTRIBUTE) * 100, 10)
        embed.add_field(
            name=f"{attr_info['emoji']} {attr_info['name']} — **{val}**",
            value=f"`{bar}`\n*{attr_info['description']}*",
            inline=False
        )
    if player.get("attr_points", 0) > 0:
        embed.add_field(
            name="💡 Attribute Points Available",
            value=f"**{player['attr_points']}** points to spend! Use `/levelup <attribute>`",
            inline=False
        )
    embed.set_footer(text="⚡ Attributes increase via /levelup • Max 20")
    return embed


# ─────────────────────────────────────────────────────────────
#  Combat
# ─────────────────────────────────────────────────────────────
def combat_embed(
    player: dict, player_hp: int, player_max_hp: int,
    enemy_name: str, enemy_hp: int, enemy_max_hp: int,
    turn: int, log: list[str], enemy_emoji: str = "👾"
) -> discord.Embed:
    player_hp_bar = hp_bar(player_hp, player_max_hp, 10)
    enemy_hp_bar = hp_bar(enemy_hp, enemy_max_hp, 10)

    embed = discord.Embed(
        title=f"⚔️ COMBAT — Turn {turn}",
        color=config.COLORS["red"]
    )
    embed.add_field(
        name=f"🧑‍💻 {player['username']}",
        value=f"`{player_hp_bar}`",
        inline=True
    )
    embed.add_field(name="VS", value="⚡", inline=True)
    embed.add_field(
        name=f"{enemy_emoji} {enemy_name}",
        value=f"`{enemy_hp_bar}`",
        inline=True
    )

    if log:
        recent = log[-5:] if len(log) > 5 else log
        embed.add_field(
            name="📜 Combat Log",
            value="\n".join(f"• {line}" for line in recent),
            inline=False
        )
    embed.set_footer(text="Choose your action below ↓")
    return embed


def combat_victory_embed(player: dict, enemy_name: str, xp: int, eddies: int, loot: list[str]) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏆 VICTORY — {enemy_name} Defeated!",
        description=f"**{player['username']}** emerges victorious from the firefight.",
        color=config.COLORS["green"]
    )
    embed.add_field(name="⭐ XP Gained", value=f"**+{xp:,}**", inline=True)
    embed.add_field(name="💰 Eddies Looted", value=f"**+{eddies:,} €$**", inline=True)
    if loot:
        loot_display = []
        for item_id in loot:
            item = get_item(item_id)
            name = item["name"] if item else item_id
            emoji = get_rarity_emoji(item.get("rarity", "common")) if item else "⬜"
            loot_display.append(f"{emoji} {name}")
        embed.add_field(name="📦 Loot Dropped", value="\n".join(loot_display), inline=False)
    return embed


def combat_defeat_embed(player: dict, enemy_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="💀 FLATLINED",
        description=(
            f"**{player['username']}** has been flatlined by **{enemy_name}**.\n\n"
            "*You wake up at the nearest ripperdoc, lighter in the wallet.*\n"
            "*Lost 10% of your eddies as medical fees.*"
        ),
        color=config.COLORS["red"]
    )
    embed.set_footer(text="Use /heal to recover HP before your next fight.")
    return embed


# ─────────────────────────────────────────────────────────────
#  Inventory
# ─────────────────────────────────────────────────────────────
def inventory_embed(player: dict, inventory: list[dict], page: int = 0, page_size: int = 10) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎒 {player['username']}'s Inventory",
        color=config.COLORS["cyan"]
    )
    total = len(inventory)
    start = page * page_size
    end = min(start + page_size, total)
    page_items = inventory[start:end]

    if not inventory:
        embed.description = "*Your inventory is empty. Time to loot some bodies.*"
    else:
        lines = []
        for row in page_items:
            item = get_item(row["item_id"])
            if item:
                emoji = get_rarity_emoji(item.get("rarity", "common"))
                name = item["name"]
                qty = f" x{row['quantity']}" if row["quantity"] > 1 else ""
                equipped_tag = " ✅ **[Equipped]**" if row["equipped"] else ""
                lines.append(f"{emoji} {name}{qty}{equipped_tag}")
            else:
                lines.append(f"⬜ {row['item_id']} x{row['quantity']}")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {page+1}/{max(1, math.ceil(total/page_size))} • {total} items total")

    return embed


def item_detail_embed(item: dict) -> discord.Embed:
    rarity = item.get("rarity", "common")
    color = get_rarity_color(rarity)
    emoji = get_rarity_emoji(rarity)
    embed = discord.Embed(
        title=f"{emoji} {item['name']}",
        description=item.get("description", ""),
        color=color
    )
    embed.add_field(name="Type", value=item.get("weapon_type", item.get("armor_slot", item.get("type", ""))).title(), inline=True)
    embed.add_field(name="Rarity", value=config.RARITIES.get(rarity, {}).get("name", rarity), inline=True)

    if item.get("damage"):
        embed.add_field(name="⚔️ Damage", value=str(item["damage"]), inline=True)
    if item.get("armor"):
        embed.add_field(name="🛡️ Armor", value=str(item["armor"]), inline=True)
    if item.get("crit_chance"):
        embed.add_field(name="🎯 Crit Chance", value=f"+{item['crit_chance']}%", inline=True)
    if item.get("heal_amount"):
        embed.add_field(name="💊 Heals", value=f"{item['heal_amount']} HP", inline=True)
    if item.get("required_level", 1) > 1:
        embed.add_field(name="📊 Required Level", value=str(item["required_level"]), inline=True)
    if item.get("buy_price"):
        embed.add_field(name="💰 Buy Price", value=f"{item['buy_price']:,} €$", inline=True)

    lore = item.get("lore")
    if not lore:
        lore = item.get("description", "")
    if lore:
        embed.add_field(name="📖 Lore", value=f"*{lore}*", inline=False)
    return embed


# ─────────────────────────────────────────────────────────────
#  Shop
# ─────────────────────────────────────────────────────────────
def shop_embed(shop_name: str, items: list[dict], player_eddies: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏪 {shop_name}",
        description=f"Your Eddies: **{player_eddies:,} €$**\nUse `/buy <item name>` to purchase.",
        color=config.COLORS["yellow"]
    )
    for item in items:
        rarity_emoji = get_rarity_emoji(item.get("rarity", "common"))
        price = int(item.get("buy_price", 0) * config.VENDOR_MARKUP)
        can_afford = "✅" if player_eddies >= price else "❌"
        desc = item.get("description", "")[:60]
        name_line = f"{rarity_emoji} **{item['name']}** — {price:,} €$ {can_afford}"
        embed.add_field(name=name_line, value=f"*{desc}*", inline=False)
    if not items:
        embed.description += "\n\n*Nothing in stock right now.*"
    return embed


# ─────────────────────────────────────────────────────────────
#  Location & Exploration
# ─────────────────────────────────────────────────────────────
def location_embed(loc: dict) -> discord.Embed:
    district_id = loc.get("district", "")
    color = config.DISTRICT_COLORS.get(district_id, config.COLORS["cyan"])
    embed = discord.Embed(
        title=f"{loc.get('emoji','🏙️')} {loc['name']}",
        description=loc.get("description", ""),
        color=color
    )
    gangs = loc.get("gangs", [])
    if gangs:
        gang_display = []
        for g in gangs:
            ginfo = config.FACTIONS.get(g, {})
            gang_display.append(f"{ginfo.get('emoji','')} {ginfo.get('name', g)}")
        embed.add_field(name="⚠️ Active Factions", value=", ".join(gang_display), inline=True)

    danger = loc.get("danger_level", 1)
    danger_str = "⚡" * danger + "░" * (5 - danger)
    embed.add_field(name="☠️ Danger Level", value=f"`{danger_str}` {danger}/5", inline=True)
    embed.add_field(name="📊 Recommended Level", value=f"Lv. {loc.get('recommended_level', 1)}+", inline=True)

    shops = loc.get("shops", [])
    if shops:
        shop_names = [s.replace("_", " ").title() for s in shops]
        embed.add_field(name="🏪 Services", value=", ".join(shop_names), inline=False)

    ambient = loc.get("ambient", [])
    if ambient:
        import random
        embed.add_field(
            name="👁️ You Notice...",
            value=f"*{random.choice(ambient)}*",
            inline=False
        )
    embed.set_footer(text="Use /explore to search the area • /travel to move")
    return embed


def map_embed(player: dict) -> discord.Embed:
    from utils.helpers import load_data
    locs = load_data("locations.json")
    districts = locs.get("districts", {})

    embed = discord.Embed(
        title="🗺️ NIGHT CITY MAP",
        description=f"You are currently in: **{get_location(player['location'])['name'] if get_location(player['location']) else player['location']}**",
        color=config.COLORS["yellow"]
    )
    for did, dist in districts.items():
        recs = f"Lv. {dist.get('recommended_level', 1)}+ | Danger {'☠️'*dist.get('danger_level',1)}"
        embed.add_field(
            name=f"{dist['emoji']} {dist['name']}",
            value=f"{dist['description'][:80]}...\n*{recs}*",
            inline=False
        )
    embed.set_footer(text="/travel <location> to move between locations")
    return embed


# ─────────────────────────────────────────────────────────────
#  Missions
# ─────────────────────────────────────────────────────────────
def mission_list_embed(missions: list[dict], title: str = "📋 Available Jobs") -> discord.Embed:
    type_emoji = {"gig": "💼", "side_job": "⭐", "main_story": "🔴", "bounty": "🎯"}
    embed = discord.Embed(title=title, color=config.COLORS["orange"])
    if not missions:
        embed.description = "*No jobs available right now. Check back later.*"
        return embed
    for m in missions[:10]:
        t_emoji = type_emoji.get(m.get("type", "gig"), "💼")
        reward_str = f"{m.get('rewards',{}).get('eddies',0):,} €$ • {m.get('rewards',{}).get('xp',0):,} XP"
        embed.add_field(
            name=f"{t_emoji} **{m['name']}** — {m.get('giver','Unknown')}",
            value=(
                f"{m['description'][:100]}...\n"
                f"📊 Lv. {m.get('required_level',1)}+ | 💰 {reward_str}\n"
                f"*Use `/job start {m['id']}` to accept*"
            ),
            inline=False
        )
    return embed


def mission_status_embed(mission: dict, active: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 {mission['name']}",
        description=mission.get("story_text", {}).get("start", mission.get("description", "")),
        color=config.COLORS["cyan"]
    )
    objectives = mission.get("objectives", [])
    current_step = active.get("step", 0)
    obj_lines = []
    for obj in objectives:
        step_num = obj["step"]
        status = "✅" if step_num < current_step else ("🔷" if step_num == current_step else "⬜")
        obj_lines.append(f"{status} {obj['text']}")
    embed.add_field(name="📌 Objectives", value="\n".join(obj_lines) if obj_lines else "None", inline=False)
    rewards = mission.get("rewards", {})
    reward_str = f"XP: **{rewards.get('xp',0):,}** | Eddies: **{rewards.get('eddies',0):,} €$**"
    if rewards.get("item"):
        item = get_item(rewards["item"])
        reward_str += f" | 🎁 {item['name'] if item else rewards['item']}"
    embed.add_field(name="🏆 Rewards", value=reward_str, inline=False)
    return embed


# ─────────────────────────────────────────────────────────────
#  Cyberware
# ─────────────────────────────────────────────────────────────
def cyberware_embed(player: dict, installed: list[dict]) -> discord.Embed:
    from utils.helpers import load_data
    cw_data = load_data("cyberware.json")
    slots = cw_data.get("cyberware_slots", {})
    humanity_pct = (player["humanity"] / player["max_humanity"]) * 100 if player["max_humanity"] > 0 else 0
    hum_bar = make_progress_bar(humanity_pct, 14)

    embed = discord.Embed(
        title=f"🦾 {player['username']}'s Cyberware",
        description=(
            f"**Humanity:** `{hum_bar}` {player['humanity']}/{player['max_humanity']}\n"
            f"*Humanity decreases with each implant. Reach 0 and go cyberpsycho.*"
        ),
        color=config.COLORS["cyan"] if player["humanity"] > 30 else config.COLORS["red"]
    )

    installed_by_slot = {row["slot"]: row["cyberware_id"] for row in installed}
    for slot_id, slot_info in slots.items():
        cw_id = installed_by_slot.get(slot_id)
        if cw_id:
            cw = get_cyberware(cw_id)
            name = cw["name"] if cw else cw_id
            rarity_emoji = get_rarity_emoji(cw.get("rarity", "common")) if cw else "⬜"
            embed.add_field(
                name=f"{slot_info['emoji']} {slot_info['name']}",
                value=f"{rarity_emoji} {name}",
                inline=True
            )
        else:
            embed.add_field(
                name=f"{slot_info['emoji']} {slot_info['name']}",
                value="*— Empty —*",
                inline=True
            )
    embed.set_footer(text="/ripperdoc — install new cyberware • /cyberware remove — uninstall")
    return embed


# ─────────────────────────────────────────────────────────────
#  Skills & Perks
# ─────────────────────────────────────────────────────────────
def skills_embed(player: dict, skills: dict[str, dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {player['username']}'s Skills",
        color=config.COLORS["cyan"]
    )
    embed.add_field(
        name="💡 Available Points",
        value=f"Skill: **{player.get('skill_points',0)}** | Perk: **{player.get('perk_points',0)}**",
        inline=False
    )
    for attr_key, attr_info in config.ATTRIBUTES.items():
        attr_skills = attr_info["skills"]
        lines = []
        for skill_name in attr_skills:
            sk = skills.get(skill_name, {"level": 1, "xp": 0})
            sk_info = config.ALL_SKILLS.get(skill_name, {})
            bar = make_progress_bar((sk["level"] / 20) * 100, 8)
            lines.append(f"{sk_info.get('emoji','•')} **{sk_info.get('name', skill_name)}** Lv.{sk['level']} `{bar}`")
        embed.add_field(
            name=f"{attr_info['emoji']} {attr_info['name']} Skills",
            value="\n".join(lines),
            inline=False
        )
    embed.set_footer(text="/skills upgrade <skill> — spend skill points • /perks — view perks")
    return embed


# ─────────────────────────────────────────────────────────────
#  Factions
# ─────────────────────────────────────────────────────────────
def factions_embed(player: dict, rep: dict[str, int]) -> discord.Embed:
    embed = discord.Embed(
        title=f"🌆 {player['username']}'s Faction Standing",
        color=config.COLORS["orange"]
    )
    for faction_key, faction_info in config.FACTIONS.items():
        faction_rep = rep.get(faction_key, 0)
        if faction_rep > 50:
            standing = "Ally"
            color_char = "🟩"
        elif faction_rep > 20:
            standing = "Friendly"
            color_char = "🟨"
        elif faction_rep > 0:
            standing = "Neutral +"
            color_char = "⬜"
        elif faction_rep == 0:
            standing = "Unknown"
            color_char = "⬛"
        elif faction_rep > -20:
            standing = "Hostile"
            color_char = "🟧"
        else:
            standing = "Kill on Sight"
            color_char = "🟥"
        rep_bar = make_progress_bar((faction_rep + 100) / 200 * 100, 8)
        embed.add_field(
            name=f"{faction_info['emoji']} {faction_info['name']}",
            value=f"{color_char} **{standing}** ({faction_rep:+d})\n`{rep_bar}` *{faction_info['territory']}*",
            inline=True
        )
    return embed


# ─────────────────────────────────────────────────────────────
#  Leaderboard
# ─────────────────────────────────────────────────────────────
def leaderboard_embed(entries: list[dict], sort_by: str = "level") -> discord.Embed:
    sort_labels = {"level": "Level", "eddies": "Eddies", "street_cred": "Street Cred", "xp": "Total XP"}
    embed = discord.Embed(
        title=f"🏆 NIGHT CITY LEADERBOARD — Top {sort_labels.get(sort_by, sort_by)}",
        color=config.COLORS["gold"]
    )
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 17
    lines = []
    for i, entry in enumerate(entries):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        lp_emoji = config.LIFEPATHS.get(entry["lifepath"], {}).get("emoji", "")
        val = entry.get(sort_by, 0)
        val_str = f"{val:,}" if sort_by in ("eddies", "xp") else str(val)
        lines.append(f"{medal} **{entry['username']}** {lp_emoji} — {sort_labels.get(sort_by,'')}: **{val_str}**")
    embed.description = "\n".join(lines) if lines else "*No players yet.*"
    embed.set_footer(text="Sort: /leaderboard level | eddies | street_cred | xp")
    return embed


# ─────────────────────────────────────────────────────────────
#  Error & Info
# ─────────────────────────────────────────────────────────────
def error_embed(title: str, message: str) -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=message, color=config.COLORS["red"])


def success_embed(title: str, message: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=message, color=config.COLORS["green"])


def info_embed(title: str, message: str, color: int = None) -> discord.Embed:
    return discord.Embed(title=title, description=message, color=color or config.COLORS["cyan"])


def not_registered_embed() -> discord.Embed:
    return discord.Embed(
        title="🚫 Not Registered",
        description="You don't have a character yet!\nUse `/start` to create one and begin your life in Night City.",
        color=config.COLORS["red"]
    )


import math  # ensure math is imported for inventory_embed
