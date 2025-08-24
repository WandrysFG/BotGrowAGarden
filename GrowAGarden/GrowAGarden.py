import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime
import logging
import json
from pathlib import Path

# CONFIGURACIÓN INICIAL
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
API_URL = "https://gagapi.onrender.com/alldata"
WEATHER_URL = "https://gagapi.onrender.com/weather"

# --- Intents corregidos ---
intents = discord.Intents.default()
intents.message_content = True  # NECESARIO para que los comandos funcionen
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --- Directorio para guardar canales por servidor ---
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
CHANNELS_FILE = DATA_DIR / "channels.json"  # { "<guild_id>": "<channel_id>" }

def load_channels() -> dict[int, int]:
    if CHANNELS_FILE.exists():
        return {int(k): int(v) for k, v in json.loads(CHANNELS_FILE.read_text()).items()}
    return {}

def save_channels(channels: dict[int, int]):
    CHANNELS_FILE.write_text(json.dumps({str(k): str(v) for k, v in channels.items()}, indent=2))

channels_by_guild: dict[int, int] = load_channels()

def get_guild_channel(guild_id: int):
    channel_id = channels_by_guild.get(guild_id)
    if channel_id:
        return bot.get_channel(channel_id)
    return None

# CONFIGURACIÓN DE CATEGORÍAS
CATEGORY_CONFIG = {
    "seeds": {
        "title": "🌱 SEMILLAS DISPONIBLES",
        "emoji": "🌱",
        "color": 0x4CAF50,
        "description": "Cultiva tu jardín con estas semillas frescas"
    },
    "gear": {
        "title": "⚙️ HERRAMIENTAS & EQUIPO",
        "emoji": "⚙️", 
        "color": 0xFF9800,
        "description": "Todo lo que necesitas para mantener tu jardín"
    },
    "eggs": {
        "title": "🥚 HUEVOS ESPECIALES",
        "emoji": "🥚",
        "color": 0xFFC107,
        "description": "Huevos únicos para tu colección"
    },
    "honey": {
        "title": "🍯 MIEL DORADA",
        "emoji": "🍯",
        "color": 0xFFB300,
        "description": "La más dulce miel para tu jardín"
    },
    "cosmetics": {
        "title": "✨ COSMÉTICOS",
        "emoji": "✨",
        "color": 0xE91E63,
        "description": "Embellece tu experiencia de jardinería"
    }
}

# EMOJIS POR ITEM
ITEM_EMOJIS = {
    "Carrot": "🥕", "Corn": "🌽", "Bamboo": "🎍", "Strawberry": "🍓",
    "Mango": "🥭", "Tomato": "🍅", "Blueberry": "🫐", "Apple": "🍎",
    "Grape": "🍇", "Watermelon": "🍉", "Pumpkin": "🎃", "Potato": "🥔",
    "Cleaning Spray": "🧴", "Trowel": "🛠️", "Watering Can": "💧",
    "Recall Wrench": "🔧", "Favorite Tool": "⭐", "Harvest Tool": "🌾",
    "Shovel": "🛠️", "Fertilizer": "🌿", "Pruning Shears": "✂️",
    "Common Egg": "🥚", "Rare Egg": "🌟", "Epic Egg": "💎", 
    "Legendary Egg": "👑", "Mystery Egg": "❓",
    "Golden Honey": "🍯", "Royal Honey": "👑", "Wild Honey": "🌼",
    "Hat": "👒", "Decoration": "🎨", "Theme": "🎭"
}

# FUNCIÓN EMOJI
def get_item_emoji(item_name: str, category: str = "") -> str:
    if item_name in ITEM_EMOJIS:
        return ITEM_EMOJIS[item_name]
    category_fallbacks = {
        "seeds": "🌱", "gear": "⚙️", "eggs": "🥚", 
        "honey": "🍯", "cosmetics": "✨"
    }
    return category_fallbacks.get(category, "📦")

# FUNCIÓN OBTENER STOCK
async def fetch_stock():
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Error HTTP {resp.status} al obtener stock")
                    return {"error": f"HTTP {resp.status}"}
    except asyncio.TimeoutError:
        logger.error("Timeout al obtener stock")
        return {"error": "Timeout"}
    except Exception as e:
        logger.error(f"Error al obtener stock: {e}")
        return {"error": str(e)}

# FUNCIÓN OBTENER CLIMA
async def fetch_weather():
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(WEATHER_URL) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Error HTTP {resp.status} al obtener clima")
                    return None
    except Exception as e:
        logger.error(f"Error al obtener clima: {e}")
        return None

# EMBED PRINCIPAL
def create_main_embed(total_items: int, weather_data=None) -> discord.Embed:
    embed = discord.Embed(
        title="🌟 GROW A GARDEN - STOCK 🌟",
        description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=0x2E8B57
    )
    embed.add_field(
        name="📊 ESTADO DEL INVENTARIO",
        value=f"🔢 **{total_items}** items disponibles\n⏰ Actualizado: <t:{int(datetime.now().timestamp())}:R>\n🔄 Próxima actualización: **5 minutos**",
        inline=False
    )
    if weather_data and weather_data.get("active"):
        weather_type = weather_data.get("type", "Desconocido").capitalize()
        effects = weather_data.get("effects", [])
        effects_text = "\n".join(f"- {effect}" for effect in effects) if effects else "Ninguno"
        embed.add_field(
            name="🌦 Clima Actual",
            value=f"**Tipo:** {weather_type}\n**Efectos:**\n{effects_text}\n⏰ Última actualización: <t:{int(datetime.now().timestamp())}:R>",
            inline=False
        )
    return embed

# EMBED CATEGORÍA
def create_category_embed(category: str, items: list) -> discord.Embed:
    config = CATEGORY_CONFIG.get(category, {
        "title": category.upper(),
        "color": 0x7289DA,
        "description": f"Items de {category}"
    })
    embed = discord.Embed(
        title=config["title"],
        description=config["description"],
        color=config["color"]
    )
    if items:
        stock_lines = []
        for item in items[:15]:
            emoji = get_item_emoji(item["name"], category)
            quantity = item["quantity"]
            if quantity == 0:
                status = "❌ **AGOTADO**"
            elif quantity < 10:
                status = f"⚠️ **{quantity}** *(Pocas unidades)*"
            elif quantity < 50:
                status = f"✅ **{quantity}** disponibles"
            else:
                status = f"🔥 **{quantity}** ¡Muchas disponibles!"
            stock_lines.append(f"{emoji} `{item['name']}` → {status}")
        if len(stock_lines) > 10:
            mid = len(stock_lines) // 2
            embed.add_field(
                name="📋 Disponible (Parte 1)",
                value="\n".join(stock_lines[:mid]),
                inline=True
            )
            embed.add_field(
                name="📋 Disponible (Parte 2)", 
                value="\n".join(stock_lines[mid:]),
                inline=True
            )
        else:
            embed.add_field(
                name="📋 Disponible",
                value="\n".join(stock_lines) if stock_lines else "No hay items disponibles",
                inline=False
            )
    else:
        embed.add_field(
            name="📋 Estado",
            value="🚫 No hay items disponibles en esta categoría",
            inline=False
        )
    return embed

# EVENTO BOT LISTO
@bot.event
async def on_ready():
    logger.info(f"✅ Bot conectado como {bot.user}")
    logger.info("🎯 Publicando stock en los canales configurados de cada servidor.")
    if not publicar_stock.is_running():
        publicar_stock.start()

# TAREA PUBLICAR STOCK
@tasks.loop(minutes=5)
async def publicar_stock():
    try:
        logger.info("📡 Obteniendo datos del stock...")
        data = await fetch_stock()
        weather_data = await fetch_weather()
        for guild in bot.guilds:
            channel = get_guild_channel(guild.id)
            if not channel:
                continue
            if "error" in data or "detail" in data:
                error_embed = discord.Embed(
                    title="⚠️ Error de Conexión",
                    description=f"No se pudo obtener el stock:\n```{data.get('error', data.get('detail', 'Error desconocido'))}```",
                    color=0xFF0000
                )
                error_embed.add_field(
                    name="🔄 Próximo intento",
                    value="En 5 minutos",
                    inline=False
                )
                await channel.send(embed=error_embed)
                continue
            total_items = sum(len(data.get(cat, [])) for cat in CATEGORY_CONFIG.keys())
            main_embed = create_main_embed(total_items, weather_data)
            await channel.send(embed=main_embed)
            for category in CATEGORY_CONFIG.keys():
                items = data.get(category, [])
                if items:
                    category_embed = create_category_embed(category, items)
                    await channel.send(embed=category_embed)
                    await asyncio.sleep(0.5)
            footer_embed = discord.Embed(
                description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🌟 **¡Gracias por usar Grow a Garden!** 🌟\n By: wan0116",
                color=0x7289DA
            )
            await channel.send(embed=footer_embed)
            logger.info(f"✅ Stock publicado exitosamente en {guild.name} - {total_items} items totales")
    except Exception as e:
        logger.error(f"❌ Error en publicar_stock: {e}")
        for guild in bot.guilds:
            channel = get_guild_channel(guild.id)
            if channel:
                critical_embed = discord.Embed(
                    title="🚨 Error Crítico",
                    description=f"Error interno del bot:\n```{str(e)}```",
                    color=0xFF0000
                )
                await channel.send(embed=critical_embed)

# Marca de tiempo para la última publicación por canal
last_manual_publish = {}

# Función para publicar stock manualmente
async def publicar_stock_manual(channel, forzar=False):
    now = datetime.now().timestamp()
    # Evita publicar si el loop automático acaba de hacerlo (últimos 10 segundos)
    if not forzar and channel.id in last_manual_publish and now - last_manual_publish[channel.id] < 10:
        await channel.send("⏳ Espera unos segundos antes de volver a solicitar el stock.")
        return
    last_manual_publish[channel.id] = now

    try:
        data = await fetch_stock()
        weather_data = await fetch_weather()
        
        if "error" in data or "detail" in data:
            error_embed = discord.Embed(
                title="⚠️ Error de Conexión",
                description=f"No se pudo obtener el stock:\n```{data.get('error', data.get('detail', 'Error desconocido'))}```",
                color=0xFF0000
            )
            error_embed.add_field(
                name="🔄 Próximo intento",
                value="En 5 minutos",
                inline=False
            )
            await channel.send(embed=error_embed)
            return
        
        total_items = sum(len(data.get(cat, [])) for cat in CATEGORY_CONFIG.keys())
        main_embed = create_main_embed(total_items, weather_data)
        await channel.send(embed=main_embed)
        
        for category in CATEGORY_CONFIG.keys():
            items = data.get(category, [])
            if items:
                category_embed = create_category_embed(category, items)
                await channel.send(embed=category_embed)
                await asyncio.sleep(0.5)
        
        footer_embed = discord.Embed(
            description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🌟 **¡Gracias por usar Grow a Garden!** 🌟\n By: wan0116",
            color=0x7289DA
        )
        await channel.send(embed=footer_embed)
    except Exception as e:
        logger.error(f"Error en publicar_stock_manual: {e}")

# COMANDO MANUAL
@bot.command(
    name="stock",
    aliases=["inventario", "update"],
    help="🔹 Publica todos los stocks actuales en Grow a Garden."
)
async def manual_stock_update(ctx):
    await ctx.send("🔄 Actualizando stock manualmente...")
    await publicar_stock_manual(ctx.channel)

@bot.command(
    name="setchannel",
    help="🔹 Configura el canal donde el bot publicará automáticamente el stock cada 5 minutos."
)
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    channels_by_guild[ctx.guild.id] = ctx.channel.id
    save_channels(channels_by_guild)
    await ctx.send(f"✅ Canal configurado: {ctx.channel.mention}. El bot publicará stock aquí cada 5 minutos.")

# COMANDO ELIMINAR CANAL DE PUBLICACIÓN
@bot.command(name="removebotchannel", help="🔹 Elimina el canal configurado para que el bot deje de publicar stock.")
@commands.has_permissions(administrator=True)
async def remove_bot_channel(ctx):
    guild_id = ctx.guild.id
    if guild_id in channels_by_guild:
        del channels_by_guild[guild_id]
        save_channels(channels_by_guild)
        await ctx.send(f"✅ Canal de publicación eliminado. El bot ya no enviará stock en este servidor.")
    else:
        await ctx.send("⚠️ No hay un canal configurado actualmente para publicar stock.")

@bot.command(
    name="help",
    help="🔹 Muestra la lista completa de comandos."
)
async def custom_help(ctx, command_name: str = None):
    embed = discord.Embed(
        title="🌟🍅 Grow a Garden - Comandos 🍅🌟",
        description="Aquí tienes la lista de comandos disponibles:",
        color=0x2E8B57
    )

    if command_name:
        command = bot.get_command(command_name)
        if command:
            embed.title = f"ℹ️ Ayuda: !{command_name}"
            aliases = f"Aliases: {', '.join(command.aliases)}" if command.aliases else "No tiene aliases"
            embed.add_field(name="Descripción", value=command.help or "Sin descripción disponible.", inline=False)
            embed.add_field(name="Aliases", value=aliases, inline=False)
        else:
            embed.title = "❌ Comando no encontrado"
            embed.description = f"No existe un comando llamado `{command_name}`."
        await ctx.send(embed=embed)
        return

    for cmd in bot.commands:
        if cmd.hidden:
            continue
        aliases = f" | ".join(f"!{a}" for a in cmd.aliases) if cmd.aliases else ""
        embed.add_field(
            name=f"🌱 !{cmd.name} {f'| {aliases}' if aliases else ''}",
            value=cmd.help or "Sin descripción disponible",
            inline=False
        )

    embed.set_footer(text="🌱 Usa !help <comando> para más detalles")
    await ctx.send(embed=embed)

# EJECUTAR BOT
if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ TOKEN no encontrado en las variables de entorno")
        exit(1)
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Token de Discord inválido")
    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar el bot: {e}")
