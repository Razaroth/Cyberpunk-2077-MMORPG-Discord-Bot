"""
database/db.py — Async SQLite database layer for Night City MMORPG
All methods are async using aiosqlite.
"""
from __future__ import annotations

import aiosqlite
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    # ─────────────────────────────────────────────────────────
    #  Schema Initialisation
    # ─────────────────────────────────────────────────────────
    async def initialize(self):
        conn = await self._get_conn()
        async with self._lock:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id      TEXT PRIMARY KEY,
                    username     TEXT NOT NULL,
                    lifepath     TEXT DEFAULT 'street_kid',
                    level        INTEGER DEFAULT 1,
                    xp           INTEGER DEFAULT 0,
                    eddies       INTEGER DEFAULT 2000,
                    street_cred  INTEGER DEFAULT 0,
                    location     TEXT DEFAULT 'watson_kabuki',
                    faction      TEXT DEFAULT 'none',
                    health       INTEGER DEFAULT 100,
                    max_health   INTEGER DEFAULT 100,
                    body         INTEGER DEFAULT 3,
                    reflexes     INTEGER DEFAULT 3,
                    tech         INTEGER DEFAULT 3,
                    intelligence INTEGER DEFAULT 3,
                    cool         INTEGER DEFAULT 3,
                    attr_points  INTEGER DEFAULT 0,
                    skill_points INTEGER DEFAULT 0,
                    perk_points  INTEGER DEFAULT 0,
                    humanity     INTEGER DEFAULT 100,
                    max_humanity INTEGER DEFAULT 100,
                    is_cyberpsycho INTEGER DEFAULT 0,
                    last_daily   TEXT DEFAULT NULL,
                    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active  TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    item_id   TEXT NOT NULL,
                    quantity  INTEGER DEFAULT 1,
                    equipped  INTEGER DEFAULT 0,
                    slot      TEXT DEFAULT NULL,
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS cyberware_installed (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       TEXT NOT NULL,
                    cyberware_id  TEXT NOT NULL,
                    slot          TEXT NOT NULL,
                    installed_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS skills (
                    user_id    TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    level      INTEGER DEFAULT 1,
                    xp         INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, skill_name),
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS perks_unlocked (
                    user_id  TEXT NOT NULL,
                    perk_id  TEXT NOT NULL,
                    PRIMARY KEY (user_id, perk_id),
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS faction_rep (
                    user_id    TEXT NOT NULL,
                    faction    TEXT NOT NULL,
                    reputation INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, faction),
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS active_missions (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    step       INTEGER DEFAULT 0,
                    status     TEXT DEFAULT 'active',
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, mission_id),
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS completed_missions (
                    user_id      TEXT NOT NULL,
                    mission_id   TEXT NOT NULL,
                    completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, mission_id),
                    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS combat_sessions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id    TEXT NOT NULL UNIQUE,
                    player_id     TEXT NOT NULL,
                    opponent_type TEXT NOT NULL,
                    opponent_id   TEXT,
                    player_hp     INTEGER NOT NULL,
                    opponent_hp   INTEGER NOT NULL,
                    player_max_hp INTEGER NOT NULL,
                    opp_max_hp    INTEGER NOT NULL,
                    turn          INTEGER DEFAULT 1,
                    player_turn   INTEGER DEFAULT 1,
                    status        TEXT DEFAULT 'active',
                    message_id    TEXT,
                    extra_data    TEXT DEFAULT '{}',
                    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS bounties (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    issuer_id   TEXT NOT NULL,
                    target_id   TEXT NOT NULL,
                    reward      INTEGER NOT NULL,
                    reason      TEXT DEFAULT '',
                    active      INTEGER DEFAULT 1,
                    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (issuer_id) REFERENCES players(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS trade_offers (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id      TEXT NOT NULL,
                    receiver_id    TEXT NOT NULL,
                    offer_item_id  TEXT NOT NULL,
                    offer_qty      INTEGER DEFAULT 1,
                    want_item_id   TEXT,
                    want_eddies    INTEGER DEFAULT 0,
                    status         TEXT DEFAULT 'pending',
                    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sender_id) REFERENCES players(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (receiver_id) REFERENCES players(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);
                CREATE INDEX IF NOT EXISTS idx_cyberware_user ON cyberware_installed(user_id);
                CREATE INDEX IF NOT EXISTS idx_skills_user ON skills(user_id);
                CREATE INDEX IF NOT EXISTS idx_faction_rep_user ON faction_rep(user_id);
                CREATE INDEX IF NOT EXISTS idx_missions_user ON active_missions(user_id);
            """)
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Player CRUD
    # ─────────────────────────────────────────────────────────
    async def get_player(self, user_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def player_exists(self, user_id: str) -> bool:
        return (await self.get_player(user_id)) is not None

    async def create_player(
        self, user_id: str, username: str, lifepath: str,
        body: int, reflexes: int, tech: int, intelligence: int, cool: int,
        starting_eddies: int, starting_location: str
    ):
        from config import BASE_HP, HP_PER_BODY_POINT
        max_hp = BASE_HP + (body - 3) * HP_PER_BODY_POINT
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                """INSERT INTO players
                   (user_id, username, lifepath, eddies, location,
                    body, reflexes, tech, intelligence, cool,
                    health, max_health)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, username, lifepath, starting_eddies, starting_location,
                 body, reflexes, tech, intelligence, cool, max_hp, max_hp)
            )
            # Initialize all skills at level 1
            from config import ALL_SKILLS
            for skill_name in ALL_SKILLS:
                await conn.execute(
                    "INSERT OR IGNORE INTO skills (user_id, skill_name) VALUES (?,?)",
                    (user_id, skill_name)
                )
            # Initialize faction reputations at 0
            from config import FACTIONS
            for faction_key in FACTIONS:
                await conn.execute(
                    "INSERT OR IGNORE INTO faction_rep (user_id, faction) VALUES (?,?)",
                    (user_id, faction_key)
                )
            await conn.commit()

    async def update_player(self, user_id: str, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                f"UPDATE players SET {cols} WHERE user_id = ?", vals
            )
            await conn.commit()

    async def add_xp(self, user_id: str, amount: int) -> dict:
        """Add XP, handle level-ups. Returns {'leveled_up': bool, 'new_level': int}."""
        from config import XP_REQUIREMENTS, MAX_LEVEL, BASE_HP, HP_PER_BODY_POINT
        player = await self.get_player(user_id)
        if not player:
            return {"leveled_up": False, "new_level": 0}
        new_xp = player["xp"] + amount
        current_level = player["level"]
        new_level = current_level
        attr_pts = 0
        skill_pts = 0
        perk_pts = 0
        while new_level < MAX_LEVEL and new_xp >= XP_REQUIREMENTS.get(new_level + 1, float("inf")):
            new_level += 1
            attr_pts += 1
            skill_pts += 2
            perk_pts += 1
        leveled_up = new_level > current_level
        updates: dict[str, Any] = {"xp": new_xp, "last_active": datetime.now(timezone.utc).isoformat()}
        if leveled_up:
            updates["level"] = new_level
            updates["attr_points"] = player["attr_points"] + attr_pts
            updates["skill_points"] = player["skill_points"] + skill_pts
            updates["perk_points"] = player["perk_points"] + perk_pts
            new_max_hp = BASE_HP + (player["body"] - 3) * HP_PER_BODY_POINT + (new_level - 1) * 5
            updates["max_health"] = new_max_hp
        await self.update_player(user_id, **updates)
        return {"leveled_up": leveled_up, "new_level": new_level, "levels_gained": new_level - current_level}

    async def add_eddies(self, user_id: str, amount: int):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE players SET eddies = MAX(0, eddies + ?) WHERE user_id = ?",
                (amount, user_id)
            )
            await conn.commit()

    async def add_street_cred(self, user_id: str, amount: int):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE players SET street_cred = MIN(100, street_cred + ?) WHERE user_id = ?",
                (amount, user_id)
            )
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Inventory
    # ─────────────────────────────────────────────────────────
    async def get_inventory(self, user_id: str) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM inventory WHERE user_id = ? ORDER BY equipped DESC, item_id",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_inventory_item(self, user_id: str, item_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def add_item(self, user_id: str, item_id: str, quantity: int = 1):
        conn = await self._get_conn()
        existing = await self.get_inventory_item(user_id, item_id)
        async with self._lock:
            if existing:
                await conn.execute(
                    "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?",
                    (quantity, user_id, item_id)
                )
            else:
                await conn.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?,?,?)",
                    (user_id, item_id, quantity)
                )
            await conn.commit()

    async def remove_item(self, user_id: str, item_id: str, quantity: int = 1) -> bool:
        existing = await self.get_inventory_item(user_id, item_id)
        if not existing or existing["quantity"] < quantity:
            return False
        conn = await self._get_conn()
        async with self._lock:
            if existing["quantity"] == quantity:
                await conn.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND item_id = ?",
                    (user_id, item_id)
                )
            else:
                await conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
                    (quantity, user_id, item_id)
                )
            await conn.commit()
        return True

    async def equip_item(self, user_id: str, item_id: str, slot: str) -> bool:
        existing = await self.get_inventory_item(user_id, item_id)
        if not existing:
            return False
        conn = await self._get_conn()
        async with self._lock:
            # Unequip existing item in that slot
            await conn.execute(
                "UPDATE inventory SET equipped = 0, slot = NULL WHERE user_id = ? AND slot = ?",
                (user_id, slot)
            )
            await conn.execute(
                "UPDATE inventory SET equipped = 1, slot = ? WHERE user_id = ? AND item_id = ?",
                (slot, user_id, item_id)
            )
            await conn.commit()
        return True

    async def unequip_slot(self, user_id: str, slot: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE inventory SET equipped = 0, slot = NULL WHERE user_id = ? AND slot = ?",
                (user_id, slot)
            )
            await conn.commit()

    async def get_equipped_items(self, user_id: str) -> dict[str, str]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT slot, item_id FROM inventory WHERE user_id = ? AND equipped = 1",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return {r["slot"]: r["item_id"] for r in rows}

    async def get_inventory_count(self, user_id: str) -> int:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT COUNT(*) as cnt FROM inventory WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row["cnt"] if row else 0

    # ─────────────────────────────────────────────────────────
    #  Cyberware
    # ─────────────────────────────────────────────────────────
    async def get_cyberware(self, user_id: str) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM cyberware_installed WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_cyberware_in_slot(self, user_id: str, slot: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM cyberware_installed WHERE user_id = ? AND slot = ?",
            (user_id, slot)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def install_cyberware(self, user_id: str, cyberware_id: str, slot: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR REPLACE INTO cyberware_installed (user_id, cyberware_id, slot) VALUES (?,?,?)",
                (user_id, cyberware_id, slot)
            )
            await conn.commit()

    async def remove_cyberware_by_slot(self, user_id: str, slot: str) -> Optional[str]:
        """Remove cyberware by slot (returns the removed cyberware_id)."""
        existing = await self.get_cyberware_in_slot(user_id, slot)
        if not existing:
            return None
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "DELETE FROM cyberware_installed WHERE user_id = ? AND slot = ?",
                (user_id, slot)
            )
            await conn.commit()
        return existing["cyberware_id"]

    # ─────────────────────────────────────────────────────────
    #  Skills
    # ─────────────────────────────────────────────────────────
    async def add_skill_xp(self, user_id: str, skill_name: str, amount: int) -> dict:
        """Add XP to a skill. Returns leveled_up info."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM skills WHERE user_id = ? AND skill_name = ?",
            (user_id, skill_name)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {"leveled_up": False}
        new_xp = row["xp"] + amount
        current_level = row["level"]
        threshold = int(100 * (current_level ** 1.5))
        new_level = current_level
        while new_xp >= threshold and new_level < 20:
            new_xp -= threshold
            new_level += 1
            threshold = int(100 * (new_level ** 1.5))
        async with self._lock:
            await conn.execute(
                "UPDATE skills SET xp = ?, level = ? WHERE user_id = ? AND skill_name = ?",
                (new_xp, new_level, user_id, skill_name)
            )
            await conn.commit()
        return {"leveled_up": new_level > current_level, "new_level": new_level}

    async def upgrade_skill(self, user_id: str, skill_name: str) -> bool:
        player = await self.get_player(user_id)
        if not player or player["skill_points"] < 1:
            return False
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE skills SET level = MIN(20, level + 1) WHERE user_id = ? AND skill_name = ?",
                (user_id, skill_name)
            )
            await conn.execute(
                "UPDATE players SET skill_points = skill_points - 1 WHERE user_id = ?",
                (user_id,)
            )
            await conn.commit()
        return True

    # ─────────────────────────────────────────────────────────
    #  Faction Reputation
    # ─────────────────────────────────────────────────────────
    async def update_faction_rep(self, user_id: str, faction: str, amount: int):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                """INSERT INTO faction_rep (user_id, faction, reputation) VALUES (?,?,?)
                   ON CONFLICT(user_id, faction) DO UPDATE SET
                   reputation = MIN(100, MAX(-100, reputation + ?))""",
                (user_id, faction, amount, amount)
            )
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Missions
    # ─────────────────────────────────────────────────────────
    async def get_active_missions(self, user_id: str) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM active_missions WHERE user_id = ? AND status = 'active'",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["current_step"] = d.get("step", 0)
            result.append(d)
        return result

    async def get_active_mission(self, user_id: str, mission_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM active_missions WHERE user_id = ? AND mission_id = ? AND status = 'active'",
            (user_id, mission_id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["current_step"] = d.get("step", 0)
        return d

    async def start_mission(self, user_id: str, mission_id: str) -> bool:
        existing = await self.get_active_mission(user_id, mission_id)
        if existing:
            return False
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR IGNORE INTO active_missions (user_id, mission_id) VALUES (?,?)",
                (user_id, mission_id)
            )
            await conn.commit()
        return True

    async def complete_mission(self, user_id: str, mission_id: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "DELETE FROM active_missions WHERE user_id = ? AND mission_id = ?",
                (user_id, mission_id)
            )
            await conn.execute(
                "INSERT OR IGNORE INTO completed_missions (user_id, mission_id) VALUES (?,?)",
                (user_id, mission_id)
            )
            await conn.commit()

    async def has_completed_mission(self, user_id: str, mission_id: str) -> bool:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT 1 FROM completed_missions WHERE user_id = ? AND mission_id = ?",
            (user_id, mission_id)
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    # ─────────────────────────────────────────────────────────
    #  Combat Sessions
    # ─────────────────────────────────────────────────────────
    async def get_combat_session(self, channel_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM combat_sessions WHERE channel_id = ? AND status = 'active'",
            (channel_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_player_combat(self, player_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM combat_sessions WHERE player_id = ? AND status = 'active'",
            (player_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def create_combat_session(
        self, channel_id: str, player_id: str, opponent_type: str,
        opponent_id: str, player_hp: int, opponent_hp: int,
        extra_data: dict = None
    ) -> int:
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                """INSERT INTO combat_sessions
                   (channel_id, player_id, opponent_type, opponent_id,
                    player_hp, opponent_hp, player_max_hp, opp_max_hp, extra_data)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (channel_id, player_id, opponent_type, opponent_id,
                 player_hp, opponent_hp, player_hp, opponent_hp,
                 json.dumps(extra_data or {}))
            )
            await conn.commit()
        async with conn.execute("SELECT last_insert_rowid() as id") as cur:
            row = await cur.fetchone()
        return row["id"]

    async def update_combat(self, channel_id: str, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [channel_id]
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                f"UPDATE combat_sessions SET {cols} WHERE channel_id = ?", vals
            )
            await conn.commit()

    async def end_combat(self, channel_id: str, status: str = "ended"):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE combat_sessions SET status = ? WHERE channel_id = ?",
                (status, channel_id)
            )
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Leaderboard
    # ─────────────────────────────────────────────────────────
    async def get_leaderboard(self, sort_by: str = "level", limit: int = 10) -> list[dict]:
        valid = {"level", "eddies", "street_cred", "xp"}
        if sort_by not in valid:
            sort_by = "level"
        conn = await self._get_conn()
        async with conn.execute(
            f"SELECT user_id, username, level, xp, eddies, street_cred, lifepath "
            f"FROM players ORDER BY {sort_by} DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────
    #  Utility
    # ─────────────────────────────────────────────────────────
    async def heal_player(self, user_id: str, amount: int):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE players SET health = MIN(max_health, health + ?) WHERE user_id = ?",
                (amount, user_id)
            )
            await conn.commit()

    async def full_heal(self, user_id: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE players SET health = max_health WHERE user_id = ?", (user_id,)
            )
            await conn.commit()

    async def reduce_humanity(self, user_id: str, amount: int) -> int:
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE players SET humanity = MAX(0, MIN(max_humanity, humanity - ?)) WHERE user_id = ?",
                (amount, user_id)
            )
            await conn.commit()
        player = await self.get_player(user_id)
        return player["humanity"] if player else 0

    # ─────────────────────────────────────────────────────────
    #  Additional Skills / Perks helpers
    # ─────────────────────────────────────────────────────────
    async def get_skills(self, user_id: str) -> list[dict]:
        """Returns list of dicts with skill_id, level, xp."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT skill_name, level, xp FROM skills WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [{"skill_id": r["skill_name"], "level": r["level"], "xp": r["xp"]} for r in rows]

    async def get_faction_rep(self, user_id: str) -> list[dict]:
        """Returns list of dicts with faction_id and reputation."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT faction, reputation FROM faction_rep WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [{"faction_id": r["faction"], "reputation": r["reputation"]} for r in rows]

    async def get_perks(self, user_id: str) -> list[dict]:
        """Returns list of dicts with perk_id."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT perk_id FROM perks_unlocked WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [{"perk_id": r["perk_id"]} for r in rows]

    async def has_perk(self, user_id: str, perk_id: str) -> bool:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT 1 FROM perks_unlocked WHERE user_id = ? AND perk_id = ?",
            (user_id, perk_id)
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    async def unlock_perk(self, user_id: str, perk_id: str) -> bool:
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "INSERT OR IGNORE INTO perks_unlocked (user_id, perk_id) VALUES (?,?)",
                (user_id, perk_id)
            )
            await conn.commit()
        return True

    # ─────────────────────────────────────────────────────────
    #  Missions — extra helpers
    # ─────────────────────────────────────────────────────────
    async def get_completed_mission_ids(self, user_id: str) -> list[str]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT mission_id FROM completed_missions WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [r["mission_id"] for r in rows]

    async def abandon_mission(self, user_id: str, mission_id: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "DELETE FROM active_missions WHERE user_id = ? AND mission_id = ?",
                (user_id, mission_id)
            )
            await conn.commit()

    async def advance_mission(self, user_id: str, mission_id: str, new_step: int):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE active_missions SET step = ? WHERE user_id = ? AND mission_id = ?",
                (new_step, user_id, mission_id)
            )
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Cyberware — remove by cyberware_id (not slot)
    # ─────────────────────────────────────────────────────────
    async def remove_cyberware(self, user_id: str, cyberware_id: str):
        """Remove a specific cyberware by its ID."""
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "DELETE FROM cyberware_installed WHERE user_id = ? AND cyberware_id = ?",
                (user_id, cyberware_id)
            )
            await conn.commit()

    # ─────────────────────────────────────────────────────────
    #  Bounties — re-exposed with consistent param names
    # ─────────────────────────────────────────────────────────
    async def place_bounty(self, placer_id: str, target_id: str, amount: int, reason: str = "") -> bool:
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "INSERT INTO bounties (issuer_id, target_id, reward, reason) VALUES (?,?,?,?)",
                (placer_id, target_id, amount, reason)
            )
            await conn.commit()
        return True

    async def get_bounties_on(self, target_id: str) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            """SELECT b.*, p.username as placer_username
               FROM bounties b
               LEFT JOIN players p ON p.user_id = b.issuer_id
               WHERE b.target_id = ? AND b.active = 1
               ORDER BY b.reward DESC""",
            (target_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_all_bounties(self) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            """SELECT b.target_id, SUM(b.reward) as total_amount,
                      p.username as target_username,
                      MAX(b.reason) as latest_reason
               FROM bounties b
               LEFT JOIN players p ON p.user_id = b.target_id
               WHERE b.active = 1
               GROUP BY b.target_id
               ORDER BY total_amount DESC LIMIT 20"""
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def collect_bounty(self, target_id: str, collector_id: str) -> int:
        """Collect all bounties on a target. Returns total reward."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT SUM(reward) as total FROM bounties WHERE target_id = ? AND active = 1",
            (target_id,)
        ) as cur:
            row = await cur.fetchone()
        total = row["total"] or 0
        if total > 0:
            async with self._lock:
                await conn.execute(
                    "UPDATE bounties SET active = 0 WHERE target_id = ?", (target_id,)
                )
                await conn.execute(
                    "UPDATE players SET eddies = eddies + ? WHERE user_id = ?",
                    (total, collector_id)
                )
                await conn.commit()
        return total

    # ─────────────────────────────────────────────────────────
    #  Trade Offers
    # ─────────────────────────────────────────────────────────
    async def create_trade_offer(
        self, from_id: str, to_id: str,
        give_item: str, give_qty: int,
        want_item: str = None, want_eddies: int = 0
    ) -> int:
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                """INSERT INTO trade_offers
                   (sender_id, receiver_id, offer_item_id, offer_qty, want_item_id, want_eddies)
                   VALUES (?,?,?,?,?,?)""",
                (from_id, to_id, give_item, give_qty, want_item, want_eddies)
            )
            await conn.commit()
        async with conn.execute("SELECT last_insert_rowid() as id") as cur:
            row = await cur.fetchone()
        return row["id"]

    async def get_trade_offer(self, trade_id: int) -> Optional[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM trade_offers WHERE id = ?", (trade_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        # Normalize field names for the cog
        d["from_id"] = d["sender_id"]
        d["to_id"] = d["receiver_id"]
        d["give_item"] = d["offer_item_id"]
        d["give_qty"] = d["offer_qty"]
        d["want_item"] = d["want_item_id"]
        return d

    async def close_trade_offer(self, trade_id: int, status: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute(
                "UPDATE trade_offers SET status = ? WHERE id = ?", (status, trade_id)
            )
            await conn.commit()

    async def get_pending_trades(self, user_id: str) -> list[dict]:
        conn = await self._get_conn()
        async with conn.execute(
            """SELECT * FROM trade_offers
               WHERE (sender_id = ? OR receiver_id = ?) AND status = 'pending'
               ORDER BY created_at DESC LIMIT 20""",
            (user_id, user_id)
        ) as cur:
            rows = await cur.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["from_id"] = d["sender_id"]
            d["to_id"] = d["receiver_id"]
            d["give_item"] = d["offer_item_id"]
            d["give_qty"] = d["offer_qty"]
            results.append(d)
        return results

    # ─────────────────────────────────────────────────────────
    #  Admin / Meta
    # ─────────────────────────────────────────────────────────
    async def delete_player(self, user_id: str):
        conn = await self._get_conn()
        async with self._lock:
            await conn.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
            await conn.commit()

    async def get_player_count(self) -> int:
        conn = await self._get_conn()
        async with conn.execute("SELECT COUNT(*) as cnt FROM players") as cur:
            row = await cur.fetchone()
        return row["cnt"] if row else 0

    async def get_active_combat_count(self) -> int:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT COUNT(*) as cnt FROM combat_sessions WHERE status = 'active'"
        ) as cur:
            row = await cur.fetchone()
        return row["cnt"] if row else 0

    # ─────────────────────────────────────────────────────────
    #  News / Recent Events feed
    # ─────────────────────────────────────────────────────────
    async def get_recent_events(self, limit: int = 10) -> list[dict]:
        """Return recent player activity as news items."""
        conn = await self._get_conn()
        events = []
        # Recent level-ups / high-level players
        async with conn.execute(
            "SELECT username, level, street_cred, location FROM players ORDER BY last_active DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
        for r in rows:
            events.append({
                "headline": f"🏙️ {r['username']} spotted in Night City",
                "body": f"Level {r['level']} — Street Cred: {r['street_cred']} — Location: {r['location'].replace('_', ' ').title()}"
            })
        return events[:limit]

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
