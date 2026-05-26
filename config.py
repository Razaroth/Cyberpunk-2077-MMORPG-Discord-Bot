"""
config.py — Global constants and game balance settings for Night City MMORPG
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Bot Settings
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
APPLICATION_ID = os.getenv("APPLICATION_ID")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
DATABASE_PATH = os.getenv("DATABASE_PATH", "cyberpunk.db")
GUILD_ID = os.getenv("GUILD_ID")

# ─────────────────────────────────────────────────────────────
#  Cyberpunk Color Palette
# ─────────────────────────────────────────────────────────────
COLORS = {
    "yellow":  0xFFE800,   # Signature CP2077 yellow
    "cyan":    0x00E5FF,   # Tech / netrunning
    "red":     0xFF003C,   # Combat / danger / iconic
    "purple":  0x9B59B6,   # Epic rarity
    "orange":  0xFF6B35,   # Warning / uncommon
    "green":   0x2ECC71,   # Healing / success
    "blue":    0x3498DB,   # Rare rarity
    "white":   0xECF0F1,   # Common items
    "dark":    0x1A1A2E,   # Dark embed background stand-in
    "gold":    0xF39C12,   # Legendary
}

# ─────────────────────────────────────────────────────────────
#  Item Rarities
# ─────────────────────────────────────────────────────────────
RARITIES = {
    "common":    {"name": "Common",    "color": COLORS["white"],  "emoji": "⬜", "price_mult": 1.0},
    "uncommon":  {"name": "Uncommon",  "color": COLORS["green"],  "emoji": "🟩", "price_mult": 1.8},
    "rare":      {"name": "Rare",      "color": COLORS["blue"],   "emoji": "🟦", "price_mult": 3.5},
    "epic":      {"name": "Epic",      "color": COLORS["purple"], "emoji": "🟪", "price_mult": 7.0},
    "legendary": {"name": "Legendary", "color": COLORS["gold"],   "emoji": "🟨", "price_mult": 15.0},
    "iconic":    {"name": "Iconic",    "color": COLORS["red"],    "emoji": "🔴", "price_mult": 30.0},
}

# ─────────────────────────────────────────────────────────────
#  Lifepaths
# ─────────────────────────────────────────────────────────────
LIFEPATHS = {
    "street_kid": {
        "name": "Street Kid",
        "description": (
            "You grew up on the streets of Night City — Watson alleyways, "
            "Heywood corners. Hard life made you harder. You know the underground, "
            "the fixers, the gangs. The city is your playground and your cage."
        ),
        "bonus_attr": "cool",
        "starting_eddies": 2500,
        "starting_bonus": "+1 Cool • 500 extra eddies • Black market contacts",
        "emoji": "🔥",
        "starting_location": "watson_kabuki",
    },
    "nomad": {
        "name": "Nomad",
        "description": (
            "You rode in from the Badlands with your clan. No corporate ID, "
            "no city upbringing — just grit, grease, and the open road. "
            "You fix what's broken and drive like the devil's behind you."
        ),
        "bonus_attr": "body",
        "starting_eddies": 1500,
        "starting_bonus": "+1 Body • Vehicle expertise • Aldecaldos contacts",
        "emoji": "🏜️",
        "starting_location": "badlands_nomad_camp",
    },
    "corpo": {
        "name": "Corpo",
        "description": (
            "You climbed the Arasaka ladder with a smile and a knife behind your back. "
            "You wore expensive suits, attended boardroom executions, and called it business. "
            "Until they burned you. Now you're on the street — but you know how power works."
        ),
        "bonus_attr": "intelligence",
        "starting_eddies": 4000,
        "starting_bonus": "+1 Intelligence • Corporate safehouses • Militech contacts",
        "emoji": "💼",
        "starting_location": "city_center_corporate_plaza",
    },
}

# ─────────────────────────────────────────────────────────────
#  Core Attributes
# ─────────────────────────────────────────────────────────────
ATTRIBUTES = {
    "body": {
        "name": "Body",
        "description": "Raw physical power. Governs HP, melee damage, and forcing doors.",
        "emoji": "💪",
        "skills": ["athletics", "annihilation", "street_brawler"],
    },
    "reflexes": {
        "name": "Reflexes",
        "description": "Speed, agility, and combat precision. Governs dodge and crit chance.",
        "emoji": "⚡",
        "skills": ["assault", "handguns", "blades"],
    },
    "tech": {
        "name": "Technical Ability",
        "description": "Engineering know-how. Governs crafting, cyberware bonuses, and tech weapons.",
        "emoji": "🔧",
        "skills": ["crafting", "engineering"],
    },
    "intelligence": {
        "name": "Intelligence",
        "description": "Netrunning capability. Governs quickhacks and breach protocol.",
        "emoji": "🧠",
        "skills": ["breach_protocol", "quickhacking"],
    },
    "cool": {
        "name": "Cool",
        "description": "Composure under pressure. Governs stealth, sniper damage, and intimidation.",
        "emoji": "😎",
        "skills": ["cold_blood", "stealth", "ninjutsu"],
    },
}

# ─────────────────────────────────────────────────────────────
#  All Skills (flat list for easy lookup)
# ─────────────────────────────────────────────────────────────
ALL_SKILLS = {
    # Body
    "athletics":      {"name": "Athletics",      "attr": "body",         "emoji": "🏃"},
    "annihilation":   {"name": "Annihilation",   "attr": "body",         "emoji": "💥"},
    "street_brawler": {"name": "Street Brawler", "attr": "body",         "emoji": "👊"},
    # Reflexes
    "assault":        {"name": "Assault",        "attr": "reflexes",     "emoji": "🎯"},
    "handguns":       {"name": "Handguns",        "attr": "reflexes",     "emoji": "🔫"},
    "blades":         {"name": "Blades",          "attr": "reflexes",     "emoji": "🗡️"},
    # Tech
    "crafting":       {"name": "Crafting",       "attr": "tech",         "emoji": "⚙️"},
    "engineering":    {"name": "Engineering",    "attr": "tech",         "emoji": "🔩"},
    # Intelligence
    "breach_protocol":{"name": "Breach Protocol","attr": "intelligence", "emoji": "💻"},
    "quickhacking":   {"name": "Quickhacking",   "attr": "intelligence", "emoji": "🖥️"},
    # Cool
    "cold_blood":     {"name": "Cold Blood",     "attr": "cool",         "emoji": "🧊"},
    "stealth":        {"name": "Stealth",        "attr": "cool",         "emoji": "👻"},
    "ninjutsu":       {"name": "Ninjutsu",       "attr": "cool",         "emoji": "🥷"},
}

# ─────────────────────────────────────────────────────────────
#  XP Table (levels 1–50)
# ─────────────────────────────────────────────────────────────
XP_REQUIREMENTS = {
    1:  0,        2:  1000,     3:  2500,     4:  5000,     5:  9000,
    6:  14000,    7:  20000,    8:  28000,    9:  38000,    10: 50000,
    11: 65000,    12: 83000,    13: 104000,   14: 128000,   15: 156000,
    16: 188000,   17: 224000,   18: 264000,   19: 309000,   20: 360000,
    21: 420000,   22: 490000,   23: 570000,   24: 662000,   25: 767000,
    26: 887000,   27: 1024000,  28: 1180000,  29: 1358000,  30: 1560000,
    31: 1790000,  32: 2050000,  33: 2345000,  34: 2680000,  35: 3060000,
    36: 3490000,  37: 3975000,  38: 4520000,  39: 5130000,  40: 5810000,
    41: 6565000,  42: 7400000,  43: 8320000,  44: 9330000,  45: 10435000,
    46: 11640000, 47: 12950000, 48: 14370000, 49: 15905000, 50: 17560000,
}

# ─────────────────────────────────────────────────────────────
#  Street Cred Titles
# ─────────────────────────────────────────────────────────────
STREET_CRED_TITLES = [
    {"min_cred": 0,   "title": "Unknown"},
    {"min_cred": 5,   "title": "Local"},
    {"min_cred": 10,  "title": "Recognized"},
    {"min_cred": 20,  "title": "Respected"},
    {"min_cred": 35,  "title": "Feared"},
    {"min_cred": 50,  "title": "Legend"},
    {"min_cred": 75,  "title": "Night City Icon"},
    {"min_cred": 100, "title": "The Living Legend"},
]

def get_street_cred_title(cred: int) -> str:
    title = "Unknown"
    for entry in STREET_CRED_TITLES:
        if cred >= entry["min_cred"]:
            title = entry["title"]
    return title

# ─────────────────────────────────────────────────────────────
#  Factions
# ─────────────────────────────────────────────────────────────
FACTIONS = {
    "maelstrom":    {"name": "Maelstrom",       "emoji": "⚙️",  "territory": "Watson (NID)",        "color": COLORS["red"],    "pledge_bonus": "+15% weapon damage, Maelstrom members won't attack on sight"},
    "tyger_claws":  {"name": "Tyger Claws",     "emoji": "🐯",  "territory": "Westbrook/Japantown", "color": COLORS["orange"], "pledge_bonus": "+10% blades damage, discounts in Westbrook shops"},
    "valentinos":   {"name": "Valentinos",      "emoji": "❤️",  "territory": "Heywood",             "color": COLORS["yellow"], "pledge_bonus": "+10 Street Cred bonus on kills, Heywood protection"},
    "6th_street":   {"name": "6th Street",      "emoji": "🦅",  "territory": "Santo Domingo",       "color": COLORS["blue"],   "pledge_bonus": "+10% assault rifle damage, Santo Domingo patrol bonuses"},
    "animals":      {"name": "Animals",         "emoji": "🦍",  "territory": "Pacifica",            "color": COLORS["green"],  "pledge_bonus": "+20% melee damage, +15 max HP"},
    "voodoo_boys":  {"name": "Voodoo Boys",     "emoji": "💀",  "territory": "Pacifica",            "color": COLORS["purple"], "pledge_bonus": "+20% quickhack damage, net architecture access"},
    "militech":     {"name": "Militech",        "emoji": "🎖️",  "territory": "Corporate Zones",     "color": COLORS["blue"],   "pledge_bonus": "+10% gun damage, military-grade weapon discounts"},
    "arasaka":      {"name": "Arasaka",         "emoji": "⛩️",  "territory": "Corporate Plaza",     "color": COLORS["red"],    "pledge_bonus": "+10% cyberware efficiency, corporate safehouses"},
    "aldecaldos":   {"name": "Aldecaldos",      "emoji": "🔥",  "territory": "Badlands",            "color": COLORS["orange"], "pledge_bonus": "+20% travel discount, nomad vehicle bonuses"},
    "moxes":        {"name": "The Moxes",       "emoji": "💜",  "territory": "Watson/Kabuki",       "color": COLORS["purple"], "pledge_bonus": "+10% Cool, extra daily reward in Watson"},
    "ncpd":         {"name": "NCPD",            "emoji": "🚔",  "territory": "Night City",          "color": COLORS["blue"],   "pledge_bonus": "+5 Street Cred bonus on bounty collects"},
    "trauma_team":  {"name": "Trauma Team",     "emoji": "🚑",  "territory": "Night City",          "color": COLORS["cyan"],   "pledge_bonus": "Revive at 50% HP instead of 25% on defeat"},
}

# ─────────────────────────────────────────────────────────────
#  Districts & Sub-Locations (IDs used in DB)
# ─────────────────────────────────────────────────────────────
DISTRICT_COLORS = {
    "watson":       COLORS["cyan"],
    "westbrook":    COLORS["purple"],
    "city_center":  COLORS["yellow"],
    "heywood":      COLORS["orange"],
    "pacifica":     COLORS["green"],
    "santo_domingo":COLORS["red"],
    "badlands":     COLORS["gold"],
}

# ─────────────────────────────────────────────────────────────
#  Game Balance Constants
# ─────────────────────────────────────────────────────────────
MAX_LEVEL              = 50
MAX_ATTRIBUTE          = 20
MIN_ATTRIBUTE          = 3
BASE_HP                = 100
HP_PER_BODY_POINT      = 20       # Each Body point adds this much max HP
MAX_INVENTORY_SIZE     = 60
ATTRIBUTE_POINTS_ON_LEVEL = 1     # Per level up
SKILL_POINTS_ON_LEVEL  = 2
PERK_POINTS_ON_LEVEL   = 1

DAILY_EDDIES           = 500
DAILY_XP               = 300
DAILY_COOLDOWN_HOURS   = 20

CRIT_BASE_CHANCE       = 0.05     # 5% base
CRIT_PER_REFLEX_POINT  = 0.01     # +1% per Reflexes above 3
CRIT_DAMAGE_MULT       = 2.0

DODGE_BASE_CHANCE      = 0.08
DODGE_PER_REFLEX_POINT = 0.015

FLEE_BASE_CHANCE       = 0.40
FLEE_PER_COOL_POINT    = 0.02

# Humanity
HUMANITY_BASE          = 100
HUMANITY_PER_CYBERWARE = 8        # Lost per install
CYBERPSYCHO_THRESHOLD  = 0

# Economy
VENDOR_MARKUP          = 1.5      # Items cost 50% more than base price
SELL_RATIO             = 0.35     # Sell for 35% of buy price
CRAFTING_COST_RATIO    = 0.6      # Craft for 60% of buy price

# XP rewards
XP_KILL_BASE           = 50
XP_MISSION_BASE        = 500
XP_EXPLORE_BASE        = 25
XP_CRAFT_BASE          = 30

# Combat
COMBAT_TIMEOUT_SECONDS = 120      # Combat auto-expires if no action
MAX_COMBAT_ROUNDS      = 30       # Force draw after this many rounds

# Missions
MAX_ACTIVE_MISSIONS    = 5

# Skills
MAX_SKILL_LEVEL        = 20

# Inventory
INVENTORY_PAGE_SIZE    = 10

# Shop / Economy
BLACK_MARKET_CRED_REQ  = 10
TRAVEL_COST            = 200       # Flat travel cost per trip

# Humanity
MAX_HUMANITY           = 100

# Factions
FACTION_PLEDGE_REQ     = 25       # Min reputation to pledge loyalty

# Bounties
MIN_BOUNTY_AMOUNT      = 500
