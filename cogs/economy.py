"""
cogs/economy.py — Shop, buy, sell, black market, and crafting
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.embeds import (
    shop_embed, item_detail_embed, error_embed, success_embed,
    info_embed, not_registered_embed
)
from utils.helpers import (
    get_item, get_shop_inventory, buy_price, sell_price, craft_cost,
    get_rarity_emoji, format_eddies
)


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /shop ─────────────────────────────────────────────────
    @app_commands.command(name="shop", description="Browse shops available in your current location.")
    async def shop(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        from utils.helpers import get_location
        loc = get_location(player["location"])
        if not loc:
            await interaction.response.send_message(
                embed=error_embed("No Shops", "There are no shops at your current location."),
                ephemeral=True
            )
            return

        shops = loc.get("shops", [])
        if not shops:
            await interaction.response.send_message(
                embed=info_embed("No Vendors", "There are no vendors in this area. Try traveling to a bigger district.", config.COLORS["cyan"]),
                ephemeral=True
            )
            return

        # Shop selection
        shop_options = [
            discord.SelectOption(
                label=s.replace("_", " ").title(),
                value=s,
                emoji={"weapon_shop": "⚔️", "ripperdoc": "🔬", "general_store": "🏪",
                       "luxury_vendor": "💎", "black_market": "🕶️", "vehicle_shop": "🚗"}.get(s, "🏪")
            )
            for s in shops
        ]

        class ShopSelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.select(placeholder="Select a shop...", options=shop_options)
            async def select_shop(self, sel_interaction: discord.Interaction, select: discord.ui.Select):
                if str(sel_interaction.user.id) != str(interaction.user.id):
                    await sel_interaction.response.send_message("This isn't your menu!", ephemeral=True)
                    return
                shop_type = select.values[0]
                if shop_type == "black_market" and player["street_cred"] < config.BLACK_MARKET_CRED_REQ:
                    await sel_interaction.response.send_message(
                        embed=error_embed(
                            "Access Denied",
                            f"The Black Market requires **{config.BLACK_MARKET_CRED_REQ}** Street Cred.\n"
                            f"You have {player['street_cred']} Street Cred."
                        ),
                        ephemeral=True
                    )
                    return
                inventory = get_shop_inventory(shop_type)
                embed = shop_embed(shop_type, inventory, player)
                self.stop()
                await sel_interaction.response.edit_message(embed=embed, view=None)

        embed = discord.Embed(
            title="🏪 SHOPS",
            description=f"Available vendors in **{loc.get('name', player['location'])}**.\nSelect a shop to browse.",
            color=config.COLORS["cyan"]
        )
        await interaction.response.send_message(embed=embed, view=ShopSelectView(), ephemeral=True)

    # ── /buy ──────────────────────────────────────────────────
    @app_commands.command(name="buy", description="Buy an item from a shop.")
    @app_commands.describe(item_id="Item ID to buy (e.g. lexington, maxdoc_mk1).", quantity="How many to buy (default: 1).")
    async def buy(self, interaction: discord.Interaction, item_id: str, quantity: int = 1):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        item_id = item_id.lower().replace(" ", "_")
        item_data = get_item(item_id)
        if not item_data:
            await interaction.response.send_message(
                embed=error_embed("Unknown Item", f"Item `{item_id}` not found."),
                ephemeral=True
            )
            return

        # Check if this item is available in any shop at current location
        from utils.helpers import get_location
        loc = get_location(player["location"])
        available = False
        if loc:
            for shop_type in loc.get("shops", []):
                inv = get_shop_inventory(shop_type)
                if any(i == item_id for i in inv):
                    available = True
                    break

        if not available:
            await interaction.response.send_message(
                embed=error_embed("Not Available", f"**{item_data['name']}** is not sold at your current location.\nTravel to a different district and try again."),
                ephemeral=True
            )
            return

        if quantity < 1:
            quantity = 1

        price_each = buy_price(item_data)
        total_cost = price_each * quantity

        if player["eddies"] < total_cost:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds",
                    f"**{item_data['name']}** costs **{price_each:,} €$** each.\n"
                    f"Total: **{total_cost:,} €$**\n"
                    f"You have: **{player['eddies']:,} €$**"
                ),
                ephemeral=True
            )
            return

        req_level = item_data.get("required_level", 1)
        if player["level"] < req_level:
            await interaction.response.send_message(
                embed=error_embed("Level Too Low", f"**{item_data['name']}** requires Level **{req_level}**."),
                ephemeral=True
            )
            return

        await self.db.add_eddies(str(interaction.user.id), -total_cost)
        await self.db.add_item(str(interaction.user.id), item_id, quantity)

        rarity_emoji = get_rarity_emoji(item_data.get("rarity", "common"))
        embed = success_embed(
            "Purchase Complete",
            f"Bought **{quantity}x** {rarity_emoji} **{item_data['name']}**\n"
            f"Cost: **{total_cost:,} €$**\n"
            f"Remaining: **{player['eddies'] - total_cost:,} €$**"
        )
        await interaction.response.send_message(embed=embed)

    # ── /sell ─────────────────────────────────────────────────
    @app_commands.command(name="sell", description="Sell an item from your inventory.")
    @app_commands.describe(item_id="Item ID to sell.", quantity="How many to sell (default: 1).")
    async def sell(self, interaction: discord.Interaction, item_id: str, quantity: int = 1):
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
                embed=error_embed("Unknown Item", f"Could not find data for item `{item_id}`."),
                ephemeral=True
            )
            return

        if quantity < 1:
            quantity = 1
        quantity = min(quantity, inv_item["quantity"])

        price_each = sell_price(item_data)
        total = price_each * quantity

        await self.db.remove_item(str(interaction.user.id), item_id, quantity)
        await self.db.add_eddies(str(interaction.user.id), total)

        embed = success_embed(
            "Item Sold",
            f"Sold **{quantity}x {item_data['name']}** for **{total:,} €$**\n"
            f"*(Vendors buy at {int(config.SELL_RATIO * 100)}% of base price)*"
        )
        await interaction.response.send_message(embed=embed)

    # ── /craft ────────────────────────────────────────────────
    @app_commands.command(name="craft", description="Craft an item using components from your inventory.")
    @app_commands.describe(recipe_id="The recipe/item ID to craft (e.g. maxdoc_mk2).")
    async def craft(self, interaction: discord.Interaction, recipe_id: str):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        recipe_id = recipe_id.lower().replace(" ", "_")
        from utils.helpers import load_data
        recipes = load_data("items.json").get("crafting_recipes", {})
        recipe = recipes.get(recipe_id)

        if not recipe:
            await interaction.response.send_message(
                embed=error_embed("Unknown Recipe", f"Recipe `{recipe_id}` not found.\nCheck what you can craft with your current components."),
                ephemeral=True
            )
            return

        required_tech = recipe.get("required_tech", 0)
        if player["tech"] < required_tech:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Tech", f"This recipe requires **Tech {required_tech}**. You have {player['tech']}."),
                ephemeral=True
            )
            return

        ingredients = recipe.get("ingredients", {})
        missing = []
        for ing_id, qty in ingredients.items():
            inv = await self.db.get_inventory_item(str(interaction.user.id), ing_id)
            if not inv or inv["quantity"] < qty:
                have = inv["quantity"] if inv else 0
                from utils.helpers import get_item as _gi
                ing_item = _gi(ing_id)
                name = ing_item["name"] if ing_item else ing_id
                missing.append(f"• **{name}**: need {qty}, have {have}")

        if missing:
            await interaction.response.send_message(
                embed=error_embed("Missing Ingredients", "You're missing:\n" + "\n".join(missing)),
                ephemeral=True
            )
            return

        # Consume ingredients
        for ing_id, qty in ingredients.items():
            await self.db.remove_item(str(interaction.user.id), ing_id, qty)

        # Grant crafted item
        result_item_id = recipe.get("result", recipe_id)
        result_qty = recipe.get("quantity", 1)
        await self.db.add_item(str(interaction.user.id), result_item_id, result_qty)

        result_item = get_item(result_item_id)
        name = result_item["name"] if result_item else result_item_id
        rarity_emoji = get_rarity_emoji(result_item["rarity"]) if result_item else ""

        # Crafting skill XP
        await self.db.add_skill_xp(str(interaction.user.id), "crafting", 30)

        embed = success_embed(
            "Item Crafted!",
            f"Crafted **{result_qty}x** {rarity_emoji} **{name}**\n\n"
            f"*+30 Crafting skill XP*"
        )
        await interaction.response.send_message(embed=embed)

    # ── /blackmarket ──────────────────────────────────────────
    @app_commands.command(name="blackmarket", description="Access the black market (requires 10 Street Cred).")
    async def blackmarket(self, interaction: discord.Interaction):
        player = await self.db.get_player(str(interaction.user.id))
        if not player:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        if player["street_cred"] < config.BLACK_MARKET_CRED_REQ:
            await interaction.response.send_message(
                embed=error_embed(
                    "Access Denied",
                    f"The black market doesn't deal with unknowns.\n\n"
                    f"You need **{config.BLACK_MARKET_CRED_REQ}** Street Cred. You have **{player['street_cred']}**.\n\n"
                    f"*Earn street cred by completing gigs, winning duels, and taking down enemies.*"
                ),
                ephemeral=True
            )
            return

        inventory = get_shop_inventory("black_market")
        embed = shop_embed("black_market", inventory, player)
        embed.title = "🕶️ BLACK MARKET"
        embed.description = "*No questions asked. No receipts.*\n\n" + (embed.description or "")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
