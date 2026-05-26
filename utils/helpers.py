"""
utils/helpers.py — Game calculation utilities for Night City MMORPG
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Optional

import config


# ─────────────────────────────────────────────────────────────
#  Data Loaders (cached)
# ─────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_cache: dict[str, dict] = {}


def load_data(filename: str) -> dict:
    if filename not in _cache:
        with open(_DATA_DIR / filename, "r", encoding="utf-8") as f:
            _cache[filename] = json.load(f)
    return _cache[filename]


def get_item(item_id: str) -> Optional[dict]:
    items = load_data("items.json")
    for category in items.values():
        if isinstance(category, dict) and item_id in category:
            return {**category[item_id], "id": item_id}
    return None


def get_enemy(enemy_id: str) -> Optional[dict]:
    enemies = load_data("enemies.json")
    return enemies.get("enemies", {}).get(enemy_id)


def get_location(location_id: str) -> Optional[dict]:
    locs = load_data("locations.json")
    return locs.get("locations", {}).get(location_id)


def get_district(district_id: str) -> Optional[dict]:
    locs = load_data("locations.json")
    return locs.get("districts", {}).get(district_id)


def get_mission(mission_id: str) -> Optional[dict]:
    missions = load_data("missions.json")
    return missions.get("missions", {}).get(mission_id)


def get_cyberware(cw_id: str) -> Optional[dict]:
    cw = load_data("cyberware.json")
    return cw.get("cyberware", {}).get(cw_id)


def get_perk(perk_id: str) -> Optional[dict]:
    """perk_id format: 'attribute.skill.perk_name'"""
    parts = perk_id.split(".")
    if len(parts) != 3:
        return None
    attr, skill, name = parts
    perks = load_data("perks.json")
    return perks.get("perks", {}).get(attr, {}).get(skill, {}).get(name)


def get_shop_inventory(shop_type: str) -> list[dict]:
    locs = load_data("locations.json")
    shop = locs.get("shop_inventories", {}).get(shop_type, {})
    items = []
    for item_id in shop.get("items", []):
        item = get_item(item_id)
        if item:
            items.append(item)
    return items


def get_enemies_for_location(location_id: str) -> list[str]:
    location = get_location(location_id)
    if not location:
        return ["scavenger"]
    gangs = location.get("gangs", [])
    enemy_data = load_data("enemies.json")["enemies"]
    pool = [eid for eid, e in enemy_data.items() if e.get("faction") in gangs]
    if not pool:
        pool = ["scavenger"]
    return pool


def scale_enemy_to_level(enemy: dict, player_level: int) -> dict:
    """Scale an enemy's stats to match the player's level."""
    e = dict(enemy)
    level_range = e.get("level_range", [1, 10])
    target_level = min(max(player_level, level_range[0]), level_range[1])
    scale = 1.0 + (target_level - 1) * 0.08
    e["scaled_hp"] = int(e["base_hp"] * scale)
    e["scaled_damage"] = int(e["base_damage"] * scale)
    e["scaled_armor"] = int(e["base_armor"] + target_level * 0.5)
    e["scaled_xp"] = int(e["xp_reward"] * scale)
    e["scaled_level"] = target_level
    # Eddie rewards
    lo, hi = e.get("eddie_range", [50, 200])
    e["scaled_eddies"] = random.randint(int(lo * scale), int(hi * scale))
    return e


# ─────────────────────────────────────────────────────────────
#  Combat Calculations
# ─────────────────────────────────────────────────────────────
def calculate_player_stats(player: dict, equipped: dict) -> dict:
    """
    Compute effective combat stats from player data + equipment.
    Returns a dict with: damage, armor, crit_chance, dodge_chance, max_hp
    """
    items_data = load_data("items.json")

    base_damage = 10 + player["body"] * 3 + player["reflexes"] * 2

    # Weapon bonus
    weapon_item_id = equipped.get("weapon")
    weapon_dmg = 0
    weapon_type = "none"
    if weapon_item_id:
        w = get_item(weapon_item_id)
        if w:
            weapon_dmg = w.get("damage", 0)
            weapon_type = w.get("weapon_type", "none")

    # Armor from equipped items
    armor = 0
    for slot in ("head", "torso", "arms", "legs"):
        item_id = equipped.get(slot)
        if item_id:
            a = get_item(item_id)
            if a:
                armor += a.get("armor", 0)
                armor += a.get("armor_bonus", 0)

    # Crit chance
    crit_chance = (
        config.CRIT_BASE_CHANCE
        + (player["reflexes"] - 3) * config.CRIT_PER_REFLEX_POINT
    )
    if weapon_item_id:
        w = get_item(weapon_item_id)
        if w:
            crit_chance += w.get("crit_chance", 0) / 100.0

    # Dodge chance
    dodge_chance = (
        config.DODGE_BASE_CHANCE
        + (player["reflexes"] - 3) * config.DODGE_PER_REFLEX_POINT
    )

    return {
        "damage": base_damage + weapon_dmg,
        "armor": max(0, armor),
        "crit_chance": min(0.75, crit_chance),
        "dodge_chance": min(0.60, dodge_chance),
        "max_hp": player["max_health"],
        "weapon_type": weapon_type,
    }


def calculate_hit(attacker_damage: int, defender_armor: int,
                  crit_chance: float, crit_mult: float = None) -> tuple[int, bool]:
    """
    Rolls a single attack. Returns (damage_dealt, is_crit).
    """
    if crit_mult is None:
        crit_mult = config.CRIT_DAMAGE_MULT
    is_crit = random.random() < crit_chance
    raw_damage = attacker_damage
    if is_crit:
        raw_damage = int(raw_damage * crit_mult)
    # Armor reduces damage but minimum 1
    damage = max(1, raw_damage - defender_armor)
    return damage, is_crit


def calculate_flee_chance(player: dict) -> float:
    return min(
        0.90,
        config.FLEE_BASE_CHANCE + (player["cool"] - 3) * config.FLEE_PER_COOL_POINT
    )


def roll_loot(enemy: dict, player_level: int) -> list[str]:
    """Roll enemy loot table. Returns list of item_ids."""
    result = []
    for entry in enemy.get("loot_table", []):
        if random.random() < entry["chance"]:
            result.append(entry["item"])
    return result


# ─────────────────────────────────────────────────────────────
#  XP & Progression
# ─────────────────────────────────────────────────────────────
def xp_for_next_level(current_level: int) -> int:
    return config.XP_REQUIREMENTS.get(current_level + 1, 0)


def xp_to_next(player: dict) -> int:
    next_thresh = config.XP_REQUIREMENTS.get(player["level"] + 1, float("inf"))
    return max(0, int(next_thresh) - player["xp"])


def level_progress_pct(player: dict) -> float:
    if player["level"] >= config.MAX_LEVEL:
        return 100.0
    current_thresh = config.XP_REQUIREMENTS.get(player["level"], 0)
    next_thresh = config.XP_REQUIREMENTS.get(player["level"] + 1, current_thresh + 1)
    progress = player["xp"] - current_thresh
    span = next_thresh - current_thresh
    return (progress / span) * 100.0 if span > 0 else 100.0


def make_progress_bar(pct: float, length: int = 10) -> str:
    filled = int(pct / 100 * length)
    return "█" * filled + "░" * (length - filled)


# ─────────────────────────────────────────────────────────────
#  Economy
# ─────────────────────────────────────────────────────────────
def buy_price(item: dict) -> int:
    return int(item.get("buy_price", 0) * config.VENDOR_MARKUP)


def sell_price(item: dict) -> int:
    return int(item.get("buy_price", 0) * config.SELL_RATIO)


def craft_cost(item: dict) -> int:
    return int(item.get("buy_price", 0) * config.CRAFTING_COST_RATIO)


# ─────────────────────────────────────────────────────────────
#  Random Events
# ─────────────────────────────────────────────────────────────
def get_random_event(location_id: str, rarity: str = "common") -> Optional[dict]:
    locs = load_data("locations.json")
    events = locs.get("random_events", {}).get(rarity, [])
    if not events:
        return None
    return random.choice(events)


def pick_random_enemy_for_location(location_id: str, player_level: int) -> tuple[str, dict]:
    """Returns (enemy_id, scaled_enemy_dict)."""
    pool = get_enemies_for_location(location_id)
    enemy_id = random.choice(pool)
    enemy = get_enemy(enemy_id)
    if not enemy:
        enemy_id = "scavenger"
        enemy = get_enemy(enemy_id)
    scaled = scale_enemy_to_level(enemy, player_level)
    return enemy_id, scaled


# ─────────────────────────────────────────────────────────────
#  Formatting helpers
# ─────────────────────────────────────────────────────────────
def format_eddies(amount: int) -> str:
    return f"💰 {amount:,} €$"


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def hp_bar(current: int, maximum: int, length: int = 12) -> str:
    pct = current / maximum if maximum > 0 else 0
    filled = int(pct * length)
    bar = "❤️" * filled + "🖤" * (length - filled)
    return f"{bar} {current}/{maximum}"


def get_rarity_color(rarity: str) -> int:
    return config.RARITIES.get(rarity, {}).get("color", config.COLORS["white"])


def get_rarity_emoji(rarity: str) -> str:
    return config.RARITIES.get(rarity, {}).get("emoji", "⬜")


def get_weapon_skill(weapon_type: str) -> str:
    mapping = {
        "pistol": "handguns",
        "rifle": "assault",
        "shotgun": "annihilation",
        "smg": "assault",
        "sniper": "assault",
        "melee": "street_brawler",
        "blade": "blades",
        "heavy": "annihilation",
    }
    return mapping.get(weapon_type, "assault")


def all_location_ids() -> list[str]:
    locs = load_data("locations.json")
    return list(locs.get("locations", {}).keys())


def location_choices() -> list[tuple[str, str]]:
    """Returns list of (display_name, location_id) for travel menus."""
    locs = load_data("locations.json")
    return [
        (data["name"], loc_id)
        for loc_id, data in locs.get("locations", {}).items()
    ]


def get_available_missions(player: dict, completed: list[str]) -> list[dict]:
    """Return missions the player is eligible for."""
    missions_data = load_data("missions.json")
    result = []
    for mid, m in missions_data.get("missions", {}).items():
        if mid in completed:
            continue
        if player["level"] < m.get("required_level", 1):
            continue
        if player["street_cred"] < m.get("required_street_cred", 0):
            continue
        required_previous = m.get("required_missions", [])
        if any(req not in completed for req in required_previous):
            continue
        result.append({**m, "id": mid})
    return result
