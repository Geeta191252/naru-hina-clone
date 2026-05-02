import sys
import glob
import importlib
from pathlib import Path
from pyrogram import Client, idle, __version__
from pyrogram.raw.all import layer
from pyrogram.errors import FloodWait
import time
import asyncio
from datetime import date, datetime
import pytz
from aiohttp import web
from database.ia_filterdb import Media, Media2, auto_cleanup_dbs
from database.topdb import silentdb as _silentdb_for_cleanup
from database.users_chats_db import db, db2 as _usersdb2_for_cleanup
from info import *
from utils import temp
from Script import script
from plugins import web_server, check_expired_premium 
from Lucia.Bot import SilentX
from Lucia.util.keepalive import ping_server
from Lucia.Bot.clients import initialize_clients
import pyrogram.utils
from PIL import Image
import threading, time, requests
from logging_helper import LOGGER

botStartTime = time.time()
ppath = "plugins/*.py"
files = glob.glob(ppath)

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

def ping_loop():
    time.sleep(10)
    while True:
        if hasattr(temp, 'BROADCAST_RUNNING') and temp.BROADCAST_RUNNING:
            time.sleep(30)
            continue
        try:
            r = requests.get(URL, timeout=10)
            if r.status_code == 200:
                LOGGER.info("✅ Ping Successful")
            else:
                LOGGER.error(f"⚠️ Ping Failed: {r.status_code}")
        except Exception as e:
            LOGGER.error(f"❌ Exception During Ping: {e}")
        time.sleep(120)


async def cleanup_loop():
    """Periodically free DB space so we never hit the 512 MB hard limit again."""
    await asyncio.sleep(60)
    while True:
        try:
            deleted = await auto_cleanup_dbs()
            if deleted:
                LOGGER.info(f"[CLEANUP-LOOP] Removed {deleted} old files from media DB")
        except Exception as e:
            LOGGER.error(f"[CLEANUP-LOOP media] {e}")
        try:
            d2 = await _silentdb_for_cleanup.auto_cleanup()
            if d2:
                LOGGER.info(f"[CLEANUP-LOOP] Removed {d2} old user docs from topdb")
        except Exception as e:
            LOGGER.error(f"[CLEANUP-LOOP topdb] {e}")
        try:
            d3 = await db.auto_cleanup()
            if d3:
                LOGGER.info(f"[CLEANUP-LOOP] Cleaned {d3} junk docs from users-DB")
        except Exception as e:
            LOGGER.error(f"[CLEANUP-LOOP usersdb] {e}")
        try:
            d4 = await _usersdb2_for_cleanup.auto_cleanup()
            if d4:
                LOGGER.info(f"[CLEANUP-LOOP] Cleaned {d4} junk docs from users-DB2")
        except Exception as e:
            LOGGER.error(f"[CLEANUP-LOOP usersdb2] {e}")
        await asyncio.sleep(1800)  # every 30 min


async def SilentXBotz_start():
    LOGGER.info('Initalizing Your Bot!')
    # Handle Telegram FloodWait on startup (happens after frequent restarts)
    while True:
        try:
            await SilentX.start()
            break
        except FloodWait as e:
            wait_time = int(getattr(e, 'value', getattr(e, 'x', 60)))
            LOGGER.warning(f"⏳ FloodWait on startup: sleeping {wait_time}s before retry...")
            await asyncio.sleep(wait_time + 2)
        except Exception as e:
            LOGGER.error(f"❌ Startup error: {e} — retrying in 30s")
            await asyncio.sleep(30)
    bot_info = await SilentX.get_me()
    SilentX.username = bot_info.username
    await initialize_clients()
    for name in files:
        with open(name) as a:
            patt = Path(a.name)
            plugin_name = patt.stem.replace(".py", "")
            plugins_dir = Path(f"plugins/{plugin_name}.py")
            import_path = "plugins.{}".format(plugin_name)
            spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
            load = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(load)
            sys.modules["plugins." + plugin_name] = load
            LOGGER.info("Import Plugins - " + plugin_name)
    if ON_HEROKU:
        asyncio.create_task(ping_server()) 
    b_users, b_chats = await db.get_banned()
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats

    # ===== AUTO CLEANUP: Free space if any DB is near full BEFORE creating indexes =====
    try:
        await auto_cleanup_dbs()
    except Exception as e:
        LOGGER.error(f"[STARTUP CLEANUP media] Failed: {e}")
    try:
        await db.auto_cleanup()
    except Exception as e:
        LOGGER.error(f"[STARTUP CLEANUP usersdb] Failed: {e}")
    try:
        await _usersdb2_for_cleanup.auto_cleanup()
    except Exception as e:
        LOGGER.error(f"[STARTUP CLEANUP usersdb2] Failed: {e}")
    try:
        await _silentdb_for_cleanup.auto_cleanup()
    except Exception as e:
        LOGGER.error(f"[STARTUP CLEANUP topdb] Failed: {e}")

    # Wrap ensure_indexes to survive 'over space quota' errors
    try:
        await Media.ensure_indexes()
    except Exception as e:
        LOGGER.error(f"[ensure_indexes Media] {e} — continuing without rebuilding indexes")
    if MULTIPLE_DB:
        try:
            await Media2.ensure_indexes()
            LOGGER.info("Multiple Database Mode On. Now Files Will Be Save In Second DB If First DB Is Full")
        except Exception as e:
            LOGGER.error(f"[ensure_indexes Media2] {e} — continuing")
    else:
        LOGGER.info("Single DB Mode On ! Files Will Be Save In First Database")
    me = await SilentX.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    temp.B_LINK = me.mention
    SilentX.username = '@' + me.username
    SilentX.loop.create_task(check_expired_premium(SilentX))
    SilentX.loop.create_task(cleanup_loop())
    LOGGER.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    LOGGER.info(script.LOGO)
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    await SilentX.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(temp.B_LINK, today, time))
    try:
        for admin in ADMINS:
            await SilentX.send_message(chat_id=admin, text=f"<b>๏[-ิ_•ิ]๏ {me.mention} Restarted ✅</code></b>")
    except:
        pass
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()
    threading.Thread(target=ping_loop, daemon=True).start()
    await idle()
    
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(SilentXBotz_start())
    except KeyboardInterrupt:
        LOGGER.info('Service Stopped Bye 👋')
