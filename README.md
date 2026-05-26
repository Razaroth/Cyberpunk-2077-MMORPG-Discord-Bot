# Night City MMORPG — Cyberpunk 2077 Discord Bot

A fully-featured, Cyberpunk 2077-themed MMORPG Discord bot with persistent characters, turn-based combat, cyberware, factions, missions, crafting, and PvP — all driven by slash commands.

---

## Requirements

- Python 3.10+
- A Discord Bot token ([Discord Developer Portal](https://discord.com/developers/applications))

---

## Installation

```bash
# 1. Clone / download the project folder
cd "Cyberpunk Discord MMORPG"

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# 5. Edit .env and fill in your values (see below)
notepad .env

# 6. Run the bot
python bot.py
```

---

## .env Configuration

| Variable         | Required | Description                                                          |
|------------------|----------|----------------------------------------------------------------------|
| `BOT_TOKEN`      | **Yes**  | Your Discord bot token from the Developer Portal                     |
| `APPLICATION_ID` | **Yes**  | Your bot's Application ID (for syncing slash commands)               |
| `GUILD_ID`       | No       | Guild ID to sync commands instantly to one server during development |
| `BOT_PREFIX`     | No       | Legacy text command prefix (default: `!`)                            |
| `DATABASE_PATH`  | No       | SQLite file path (default: `cyberpunk.db`)                           |

> **Tip:** Set `GUILD_ID` during development so slash commands sync in seconds instead of up to 1 hour globally.

---

## First Run

1. Invite the bot to your server with the `applications.commands` and `bot` scopes.
2. Start the bot: `python bot.py`
3. In Discord, type `/start` to create your character.

---

## Slash Command Reference

### Character
| Command | Description |
|---------|-------------|
| `/start` | Create your Night City character (choose lifepath) |
| `/profile [@user]` | View your or another player's profile card |
| `/stats` | Display detailed character attributes |
| `/levelup` | Spend attribute points when you've levelled up |
| `/daily` | Claim your daily eddies and XP (20h cooldown) |
| `/heal` | Use consumables from your inventory to restore HP |

### Combat
| Command | Description |
|---------|-------------|
| `/hunt` | Start a fight with a random enemy in your area |
| `/duel @target` | Challenge another player to PvP |

### Exploration
| Command | Description |
|---------|-------------|
| `/map` | View the full Night City district map |
| `/location` | Info about your current location |
| `/travel <destination>` | Move to another district (costs eddies) |
| `/explore` | Search your current area for loot, events, or trouble |
| `/scan` | Use Kiroshi optics to scan your surroundings |

### Inventory
| Command | Description |
|---------|-------------|
| `/inventory [page]` | Browse your inventory |
| `/equip <item>` | Equip a weapon or armor piece |
| `/unequip <slot>` | Remove an equipped item |
| `/inspect <item>` | View detailed item stats |
| `/drop <item> [qty]` | Discard an item |
| `/equipped` | View your currently equipped gear and stats |

### Economy
| Command | Description |
|---------|-------------|
| `/shop` | Browse a vendor at your current location |
| `/buy <item> [qty]` | Purchase an item |
| `/sell <item> [qty]` | Sell an item for eddies |
| `/craft <recipe>` | Craft an item from components |
| `/blackmarket` | Access the black market (requires Street Cred) |

### Missions
| Command | Description |
|---------|-------------|
| `/jobs` | List available gigs and jobs |
| `/job start <mission>` | Accept a mission |
| `/job status` | Check your active missions |
| `/job advance <mission>` | Progress to the next objective |
| `/job complete <mission>` | Turn in a completed mission |
| `/job abandon <mission>` | Drop an active mission |

### Cyberware
| Command | Description |
|---------|-------------|
| `/cyberware` | View your installed cyberware |
| `/humanity` | Check your Humanity meter |
| `/ripperdoc` | Browse cyberware at a ripperdoc clinic |
| `/install <cyberware>` | Install a new piece of cyberware |
| `/cwremove <cyberware>` | Remove installed cyberware |

### Skills & Perks
| Command | Description |
|---------|-------------|
| `/skills` | View all skill levels and XP |
| `/skillup <skill>` | Spend a skill point to raise a skill |
| `/perks [attribute]` | Browse the perk tree |
| `/perk unlock <perk>` | Unlock a perk with perk points |

### Factions & Street Cred
| Command | Description |
|---------|-------------|
| `/factions` | View all faction reputations |
| `/streetcred` | Your Street Cred rank and progress |
| `/pledge <faction>` | Pledge loyalty to a faction |
| `/bounty place @target <amount> [reason]` | Put a bounty on a player |
| `/bounty list` | View all active bounties |
| `/bounty on @target` | View bounties on a specific player |

### Social & Trading
| Command | Description |
|---------|-------------|
| `/leaderboard [sort]` | Top players by level, eddies, XP, or street cred |
| `/trade offer @user <item> ...` | Offer a trade to another player |
| `/trade accept <id>` | Accept a pending trade |
| `/trade decline <id>` | Decline a pending trade |
| `/trade list` | View your pending trades |
| `/news` | Night City news feed |

### Admin (Administrators Only)
| Command | Description |
|---------|-------------|
| `/admin give <user> <amount>` | Give eddies to a player |
| `/admin setlevel <user> <level>` | Set a player's level |
| `/admin reset <user>` | Delete a player's data |
| `/admin heal <user>` | Fully heal a player |
| `/admin giveitem <user> <item> [qty]` | Add an item to a player's inventory |
| `/admin givecred <user> <amount>` | Give Street Cred to a player |
| `/admin sethumanity <user> <value>` | Set a player's humanity |
| `/admin spawn <type>` | Trigger a world event |
| `/admin stats` | Bot statistics (players, active combats) |

---

## Game Systems

### Lifepaths
Choose your origin at character creation:
- **Street Kid** — Body + Cool bonus, starts in Watson
- **Nomad** — Body + Tech bonus, starts on the outskirts
- **Corpo** — Intelligence + Cool bonus, starts in City Center

### Attributes & Skills
Five core attributes (Body, Reflexes, Tech, Intelligence, Cool) govern 13 skills. Raise attributes with attribute points earned on level-up, and spend skill points to raise individual skills.

### Cyberware & Humanity
Install cyberware at ripperdoc locations. Each implant reduces your Humanity score. Reach 0 Humanity and you become a Cyberpsycho — a feared threat to other players.

### Factions
Build reputation with 12 factions across Night City. Reach 25 reputation to pledge allegiance and unlock faction-specific bonuses.

### Street Cred
Earn Street Cred by completing missions and winning fights. Unlock vendors, black market access, and new gigs as your cred grows.

### Combat
Turn-based combat via interactive buttons: Attack, Dodge, Quick Hack, Use Item, or Flee. Enemy AI selects special skills based on cooldowns. Cyberware passives (Gorilla Arms, Mantis Blades, Blood Pump) activate automatically.

---

## Project Structure

```
Cyberpunk Discord MMORPG/
├── bot.py                  # Entry point
├── config.py               # All constants and configuration
├── requirements.txt
├── .env.example
├── data/
│   ├── items.json
│   ├── enemies.json
│   ├── locations.json
│   ├── cyberware.json
│   ├── missions.json
│   └── perks.json
├── database/
│   ├── __init__.py
│   └── db.py               # Async SQLite layer
├── utils/
│   ├── __init__.py
│   ├── helpers.py          # Game logic helpers
│   └── embeds.py           # Discord embed builders
└── cogs/
    ├── __init__.py
    ├── character.py
    ├── combat.py
    ├── exploration.py
    ├── inventory.py
    ├── economy.py
    ├── missions.py
    ├── cyberware.py
    ├── skills.py
    ├── factions.py
    ├── social.py
    └── admin.py
```

---

## License

This is a fan project. Cyberpunk 2077 is a trademark of CD Projekt Red. This bot is not affiliated with or endorsed by CD Projekt Red.
