"""
cogs/inventory.py — Inventory management: view, equip, unequip, inspect, drop
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    inventory_embed, item_detail_embed, error_embed, success_embed,
    info_embed, not_registered_embed
)
from utils.helpers import get_item, get_rarity_color, get_rarity_emoji


ITEM_SLOTS = {
    "weapon": ["weapon"],
    "armor_chest": ["armor_chest", "armor"],
    "armor_head": ["armor_head"],
    "armor_legs": ["armor_legs"],
    "armor_hands": ["armor_hands"],
}

SLOT_DISPLAY = {
    "weapon": "Weapon",
    "armor_chest": "Chest Armor",
    "armor_head": "Head Armor",
    "armor_legs": "Leg Armor",
    "armor_hands": "Gloves",
}


class InventoryPageView(discord.ui.View):
    def __init__(self, user_id: str, db, total_pages: int, current_page: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.db = db
        self.total_pages = total_pages
        self.current_page = current_page
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current_page <= 0
        self.next_btn.disabled = self.current_page >= self.total_pages - 1

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This isn't your inventory!", ephemeral=True)
            return
        self.current_page -= 1
        self._update_buttons()
        inventory = await self.db.get_inventory(self.user_id)
        player = await self.db.get_player(self.user_id)
        embed = inventory_embed(player, inventory, self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This isn't your inventory!", ephemeral=True)
            return
        self.current_page += 1
        self._update_buttons()
        inventory = await self.db.get_inventory(self.user_id)
        player = await self.db.get_player(self.user_id)
        embed = inventory_embed(player, inventory, self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)


class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /inventory ────────────────────────────────────────────
    @app_commands.command(name="inventory", description="View your inventory.")
    @app_commands.describe(page="Page number (default: 1).")
    async def inventory(self, interaction: discord.Interaction, page: int = 1):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        inv = await self.db.get_inventory(str(interaction.user.id))
        if not inv:
            await interaction.response.send_message(
                embed=info_embed("Empty Inventory", "Your inventory is empty.\nBuy items at shops with `/shop` or find them by exploring.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        page_idx = max(0, page - 1)
        page_size = config.INVENTORY_PAGE_SIZE
        total_pages = max(1, (len(inv) + page_size - 1) // page_size)
        page_idx = min(page_idx, total_pages - 1)

        embed = inventory_embed(player, inv, page_idx)
        view = InventoryPageView(str(interaction.user.id), self.db, total_pages, page_idx)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /equip ────────────────────────────────────────────────
    @app_commands.command(name="equip", description="Equip an item from your inventory.")
    @app_commands.describe(item_id="The item ID to equip (e.g. lexington, leather_jacket).")
    async def equip(self, interaction: discord.Interaction, item_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        item_id = item_id.lower().replace(" ", "_")
        inv_item = await self.db.get_inventory_item(str(interaction.user.id), item_id)
        if not inv_item or inv_item["quantity"] < 1:
            await interaction.response.send_message(
                embed=error_embed("Item Not Found", f"You don't have `{item_id}` in your inventory."),
                ephemeral=True
            )
            return

        item_data = get_item(item_id)
        if not item_data:
            await interaction.response.send_message(
                embed=error_embed("Unknown Item", f"Item `{item_id}` doesn't exist in the game data."),
                ephemeral=True
            )
            return

        item_type = item_data.get("type", "")
        if item_type not in ("weapon", "armor", "consumable"):
            await interaction.response.send_message(
                embed=error_embed("Not Equippable", f"**{item_data['name']}** cannot be equipped. It's a consumable or crafting material."),
                ephemeral=True
            )
            return

        if item_type == "consumable":
            await interaction.response.send_message(
                embed=error_embed("Not Equippable", f"**{item_data['name']}** is a consumable. Use it with `/heal` or during combat."),
                ephemeral=True
            )
            return

        # Determine slot
        if item_type == "weapon":
            slot = "weapon"
        else:
            slot = item_data.get("slot", "armor_chest")

        # Level requirement
        req_level = item_data.get("required_level", 1)
        if player["level"] < req_level:
            await interaction.response.send_message(
                embed=error_embed("Level Too Low", f"**{item_data['name']}** requires Level **{req_level}**. You are Level {player['level']}."),
                ephemeral=True
            )
            return

        await self.db.equip_item(str(interaction.user.id), item_id, slot)

        rarity_emoji = get_rarity_emoji(item_data.get("rarity", "common"))
        embed = success_embed(
            "Item Equipped",
            f"{rarity_emoji} **{item_data['name']}** equipped to **{SLOT_DISPLAY.get(slot, slot.title())}** slot."
        )
        if item_type == "weapon":
            embed.add_field(name="⚔️ Damage", value=str(item_data.get("damage", "N/A")), inline=True)
        elif item_type == "armor":
            embed.add_field(name="🛡️ Armor", value=str(item_data.get("armor", "N/A")), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /unequip ──────────────────────────────────────────────
    @app_commands.command(name="unequip", description="Unequip an item from a slot.")
    @app_commands.describe(slot="The slot to unequip (weapon, armor_chest, armor_head, armor_legs, armor_hands).")
    @app_commands.choices(slot=[
        app_commands.Choice(name="Weapon", value="weapon"),
        app_commands.Choice(name="Chest Armor", value="armor_chest"),
        app_commands.Choice(name="Head Armor", value="armor_head"),
        app_commands.Choice(name="Leg Armor", value="armor_legs"),
        app_commands.Choice(name="Gloves", value="armor_hands"),
    ])
    async def unequip(self, interaction: discord.Interaction, slot: app_commands.Choice[str]):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        equipped = await self.db.get_equipped_items(str(interaction.user.id))
        item_id = equipped.get(slot.value)
        if not item_id:
            await interaction.response.send_message(
                embed=info_embed("Nothing Equipped", f"You have nothing equipped in the **{slot.name}** slot.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        await self.db.unequip_slot(str(interaction.user.id), slot.value)
        item_data = get_item(item_id)
        name = item_data["name"] if item_data else item_id
        await interaction.response.send_message(
            embed=success_embed("Item Unequipped", f"**{name}** has been moved back to your inventory.")
        )

    # ── /inspect ──────────────────────────────────────────────
    @app_commands.command(name="inspect", description="Inspect an item to view its details.")
    @app_commands.describe(item_id="The item ID to inspect (e.g. lexington, maxdoc_mk1).")
    async def inspect(self, interaction: discord.Interaction, item_id: str):
        item_id = item_id.lower().replace(" ", "_")
        item_data = get_item(item_id)
        if not item_data:
            await interaction.response.send_message(
                embed=error_embed("Unknown Item", f"Item `{item_id}` not found. Check the spelling."),
                ephemeral=True
            )
            return
        await interaction.response.send_message(embed=item_detail_embed(item_data))

    # ── /drop ─────────────────────────────────────────────────
    @app_commands.command(name="drop", description="Drop (delete) an item from your inventory.")
    @app_commands.describe(item_id="The item ID to drop.", quantity="How many to drop (default: 1).")
    async def drop(self, interaction: discord.Interaction, item_id: str, quantity: int = 1):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        item_id = item_id.lower().replace(" ", "_")
        inv_item = await self.db.get_inventory_item(str(interaction.user.id), item_id)
        if not inv_item or inv_item["quantity"] < 1:
            await interaction.response.send_message(
                embed=error_embed("Item Not Found", f"You don't have `{item_id}` in your inventory."),
                ephemeral=True
            )
            return

        if quantity < 1:
            quantity = 1
        quantity = min(quantity, inv_item["quantity"])

        item_data = get_item(item_id)
        name = item_data["name"] if item_data else item_id

        # Confirm drop with a button
        class DropConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.confirmed = False

            @discord.ui.button(label="🗑️ Confirm Drop", style=discord.ButtonStyle.danger)
            async def confirm(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                if str(btn_interaction.user.id) != str(interaction.user.id):
                    await btn_interaction.response.send_message("This isn't your inventory!", ephemeral=True)
                    return
                self.confirmed = True
                self.stop()
                await btn_interaction.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.stop()
                await btn_interaction.response.edit_message(
                    embed=info_embed("Cancelled", "Item drop cancelled.", config.COLORS["cyan"]),
                    view=None
                )

        view = DropConfirmView()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Drop Item",
                description=f"Are you sure you want to drop **{quantity}x {name}**?\n\nThis cannot be undone.",
                color=config.COLORS["yellow"]
            ),
            view=view,
            ephemeral=True
        )
        await view.wait()
        if view.confirmed:
            await self.db.remove_item(str(interaction.user.id), item_id, quantity)
            await interaction.edit_original_response(
                embed=success_embed("Item Dropped", f"Dropped **{quantity}x {name}** from your inventory."),
                view=None
            )

    # ── /equipped ─────────────────────────────────────────────
    @app_commands.command(name="equipped", description="View your currently equipped items and stats.")
    async def equipped_cmd(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        equipped = await self.db.get_equipped_items(str(interaction.user.id))
        from utils.helpers import calculate_player_stats
        stats = calculate_player_stats(player, equipped)

        embed = discord.Embed(title="⚙️ Equipped Gear", color=config.COLORS["yellow"])
        for slot_key, slot_name in SLOT_DISPLAY.items():
            item_id = equipped.get(slot_key)
            if item_id:
                item = get_item(item_id)
                rarity = get_rarity_emoji(item["rarity"]) if item else ""
                value = f"{rarity} {item['name']}" if item else f"`{item_id}`"
            else:
                value = "*Empty*"
            embed.add_field(name=slot_name, value=value, inline=True)

        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="⚔️ Damage", value=str(stats["damage"]), inline=True)
        embed.add_field(name="🛡️ Armor", value=str(stats["armor"]), inline=True)
        embed.add_field(name="💥 Crit %", value=f"{stats['crit_chance']*100:.1f}%", inline=True)
        embed.add_field(name="💨 Dodge %", value=f"{stats['dodge_chance']*100:.1f}%", inline=True)
        embed.add_field(name="❤️ Max HP", value=str(stats["max_hp"]), inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
