"""
Additional bot commands:
/connect, /disconnect, /connections,
/shortlink, /shortlink_info, /setshorlinkon, /setshortlinkoff,
/set_tutorial, /remove_tutorial,
/link, /batch,
/verification

These commands integrate with the existing settings stored in the
group document (see database.users_chats_db.get_settings) and the
connection collection that maps users to groups they manage.
"""

import re
import base64
import asyncio
from logging_helper import LOGGER
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import FloodWait

from database.users_chats_db import db
from utils import get_settings, save_group_settings, is_check_admin
from info import ADMINS, BIN_CHANNEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_target_group(client, message):
    """
    Returns the group_id the user wants to act on.
    - In a group chat: that group (must be admin).
    - In PM: the user must have at least one connected group; if more than
      one, we return None and ask them to use it inside the group.
    """
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        await message.reply_text("ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")
        return None

    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await is_check_admin(client, message.chat.id, user_id):
            await message.reply_text("<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</b>")
            return None
        await db.connect_group(message.chat.id, user_id)
        return message.chat.id

    # Private chat
    groups = await db.get_connected_grps(user_id)
    if not groups:
        await message.reply_text(
            "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴀɴʏ ɢʀᴏᴜᴘ ʏᴇᴛ.\n"
            "ᴜꜱᴇ /connect ɪɴꜱɪᴅᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ꜰɪʀꜱᴛ."
        )
        return None
    if len(groups) > 1:
        await message.reply_text(
            "ʏᴏᴜ ʜᴀᴠᴇ ᴍᴜʟᴛɪᴘʟᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ.\n"
            "ᴘʟᴇᴀꜱᴇ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴅɪʀᴇᴄᴛʟʏ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ."
        )
        return None
    return groups[0]


def _encode_file(msg_id: int) -> str:
    raw = f"file_{msg_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# /connect /disconnect /connections
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("connect") & filters.user(ADMINS))
async def connect_cmd(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply_text("ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")

    chat_type = message.chat.type
    if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await is_check_admin(client, message.chat.id, user_id):
            return await message.reply_text("<b>ʏᴏᴜ ᴍᴜꜱᴛ ʙᴇ ᴀᴅᴍɪɴ ᴏꜰ ᴛʜɪꜱ ɢʀᴏᴜᴘ.</b>")
        await db.connect_group(message.chat.id, user_id)
        return await message.reply_text(
            f"✅ <b>ɢʀᴏᴜᴘ ᴄᴏɴɴᴇᴄᴛᴇᴅ.</b>\n"
            f"ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴍᴀɴᴀɢᴇ <b>{message.chat.title}</b> ꜰʀᴏᴍ ᴍʏ PM."
        )

    # PM: /connect <group_id>
    if len(message.command) < 2:
        return await message.reply_text(
            "ᴜꜱᴀɢᴇ:\n<code>/connect &lt;group_id&gt;</code>\n\n"
            "ᴏʀ ᴏᴘᴇɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴛʏᴘᴇ /connect ᴛʜᴇʀᴇ."
        )
    try:
        group_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ID.")
    try:
        if not await is_check_admin(client, group_id, user_id):
            return await message.reply_text("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ.")
        chat = await client.get_chat(group_id)
        await db.connect_group(group_id, user_id)
        await message.reply_text(f"✅ ᴄᴏɴɴᴇᴄᴛᴇᴅ <b>{chat.title}</b> ᴛᴏ ʏᴏᴜʀ PM.")
    except Exception as e:
        LOGGER.error(f"/connect error: {e}")
        await message.reply_text("❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛ. ᴄʜᴇᴄᴋ ɢʀᴏᴜᴘ ID ᴀɴᴅ ʙᴏᴛ ᴀᴄᴄᴇꜱꜱ.")


@Client.on_message(filters.command("disconnect") & filters.user(ADMINS))
async def disconnect_cmd(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply_text("ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")

    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await is_check_admin(client, message.chat.id, user_id):
            return await message.reply_text("<b>ᴀᴅᴍɪɴ ᴏɴʟʏ.</b>")
        ok = await db.disconnect_group(message.chat.id, user_id)
        return await message.reply_text(
            "✅ ɢʀᴏᴜᴘ ᴅɪꜱᴄᴏɴɴᴇᴄᴛᴇᴅ." if ok else "ᴛʜɪꜱ ɢʀᴏᴜᴘ ᴡᴀꜱɴ'ᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ."
        )

    # PM
    if len(message.command) < 2:
        groups = await db.get_connected_grps(user_id)
        if not groups:
            return await message.reply_text("ɴᴏ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ.")
        btns = []
        for gid in groups:
            try:
                chat = await client.get_chat(gid)
                title = chat.title
            except Exception:
                title = str(gid)
            btns.append([InlineKeyboardButton(f"❌ {title}", callback_data=f"disc#{gid}")])
        return await message.reply_text(
            "<b>ᴄʜᴏᴏꜱᴇ ᴀ ɢʀᴏᴜᴘ ᴛᴏ ᴅɪꜱᴄᴏɴɴᴇᴄᴛ:</b>",
            reply_markup=InlineKeyboardMarkup(btns),
        )
    try:
        gid = int(message.command[1])
        ok = await db.disconnect_group(gid, user_id)
        await message.reply_text(
            "✅ ᴅɪꜱᴄᴏɴɴᴇᴄᴛᴇᴅ." if ok else "ɢʀᴏᴜᴘ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛɪᴏɴꜱ."
        )
    except ValueError:
        await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ID.")


@Client.on_callback_query(filters.regex(r"^disc#(-?\d+)$"))
async def disconnect_cb(client, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("Not allowed.", show_alert=True)
    gid = int(query.matches[0].group(1))
    ok = await db.disconnect_group(gid, query.from_user.id)
    await query.answer("Disconnected" if ok else "Not found", show_alert=True)
    try:
        await query.message.delete()
    except Exception:
        pass


@Client.on_message(filters.command("connections") & filters.user(ADMINS))
async def connections_cmd(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return
    groups = await db.get_connected_grps(user_id)
    if not groups:
        return await message.reply_text("ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ.")
    lines = ["<b>ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘꜱ:</b>\n"]
    for i, gid in enumerate(groups, 1):
        try:
            chat = await client.get_chat(gid)
            lines.append(f"{i}. <b>{chat.title}</b> — <code>{gid}</code>")
        except Exception:
            lines.append(f"{i}. <code>{gid}</code> (info unavailable)")
    await message.reply_text("\n".join(lines))


# ---------------------------------------------------------------------------
# /shortlink /shortlink_info /setshorlinkon /setshortlinkoff
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("shortlink") & filters.user(ADMINS))
async def shortlink_cmd(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    if len(message.command) < 3:
        return await message.reply_text(
            "ᴜꜱᴀɢᴇ:\n<code>/shortlink &lt;website&gt; &lt;api_key&gt;</code>\n\n"
            "ᴇxᴀᴍᴘʟᴇ:\n<code>/shortlink shrinkme.io abc123apikey</code>"
        )
    website = message.command[1].strip().replace("https://", "").replace("http://", "").strip("/")
    api_key = message.command[2].strip()
    await save_group_settings(grp_id, "shortner", website)
    await save_group_settings(grp_id, "api", api_key)
    await save_group_settings(grp_id, "is_verify", True)
    await message.reply_text(
        f"✅ <b>ꜱʜᴏʀᴛʟɪɴᴋ ᴜᴘᴅᴀᴛᴇᴅ.</b>\n\n"
        f"🌐 ᴡᴇʙꜱɪᴛᴇ: <code>{website}</code>\n"
        f"🔑 ᴀᴘɪ: <code>{api_key[:6]}…</code>"
    )


@Client.on_message(filters.command("shortlink_info") & filters.user(ADMINS))
async def shortlink_info_cmd(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    s = await get_settings(grp_id)
    text = (
        "<b>📊 ꜱʜᴏʀᴛʟɪɴᴋ ɪɴꜰᴏ</b>\n\n"
        f"🔘 ꜱᴛᴀᴛᴜꜱ: <b>{'ON ✅' if s.get('is_verify') else 'OFF ❌'}</b>\n"
        f"🌐 ᴡᴇʙꜱɪᴛᴇ: <code>{s.get('shortner') or 'not set'}</code>\n"
        f"🔑 ᴀᴘɪ: <code>{(s.get('api') or 'not set')[:8]}…</code>\n\n"
        f"🌐 ꜱʜᴏʀᴛɴᴇʀ 2: <code>{s.get('shortner_two') or '—'}</code>\n"
        f"🌐 ꜱʜᴏʀᴛɴᴇʀ 3: <code>{s.get('shortner_three') or '—'}</code>"
    )
    await message.reply_text(text)


@Client.on_message((filters.command("setshorlinkon") | filters.command("setshortlinkon")) & filters.user(ADMINS))
async def shortlink_on(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    await save_group_settings(grp_id, "is_verify", True)
    await message.reply_text("✅ ꜱʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛᴜʀɴᴇᴅ <b>ON</b>.")


@Client.on_message(filters.command("setshortlinkoff") & filters.user(ADMINS))
async def shortlink_off(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    await save_group_settings(grp_id, "is_verify", False)
    await message.reply_text("✅ ꜱʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛᴜʀɴᴇᴅ <b>OFF</b>.")


# ---------------------------------------------------------------------------
# /set_tutorial /remove_tutorial
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("set_tutorial") & filters.user(ADMINS))
async def set_tutorial_cmd(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    if len(message.command) < 2:
        return await message.reply_text(
            "ᴜꜱᴀɢᴇ:\n<code>/set_tutorial &lt;video_link&gt;</code>"
        )
    link = message.command[1].strip()
    if not re.match(r"^https?://", link):
        return await message.reply_text("❌ ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ http(s) ʟɪɴᴋ.")
    await save_group_settings(grp_id, "tutorial", link)
    await message.reply_text(f"✅ ᴛᴜᴛᴏʀɪᴀʟ ᴜᴘᴅᴀᴛᴇᴅ:\n{link}")


@Client.on_message(filters.command("remove_tutorial") & filters.user(ADMINS))
async def remove_tutorial_cmd(client, message):
    grp_id = await _resolve_target_group(client, message)
    if grp_id is None:
        return
    await save_group_settings(grp_id, "tutorial", "")
    await message.reply_text("✅ ᴛᴜᴛᴏʀɪᴀʟ ʀᴇᴍᴏᴠᴇᴅ.")


# ---------------------------------------------------------------------------
# /link  /batch  (admin-only — generate sharable start links)
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("link") & filters.user(ADMINS))
async def link_cmd(client, message):
    """
    Reply to a file in BIN_CHANNEL (or forward) to generate a shareable
    /start?file_xxx link.
    """
    reply = message.reply_to_message
    if not reply or not reply.media:
        return await message.reply_text(
            "ᴜꜱᴀɢᴇ: ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇᴅɪᴀ ᴍᴇꜱꜱᴀɢᴇ ɪɴ ᴛʜᴇ ʟᴏɢ/ʙɪɴ ᴄʜᴀɴɴᴇʟ ᴡɪᴛʜ /link"
        )
    try:
        # Copy the message into BIN_CHANNEL so we get a stable id
        copied = await reply.copy(BIN_CHANNEL)
        encoded = _encode_file(copied.id)
        bot_username = (await client.get_me()).username
        share = f"https://t.me/{bot_username}?start={encoded}"
        await message.reply_text(
            f"✅ <b>ʟɪɴᴋ ɢᴇɴᴇʀᴀᴛᴇᴅ:</b>\n{share}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 ᴏᴘᴇɴ ʟɪɴᴋ", url=share)]]
            ),
            disable_web_page_preview=True,
        )
    except Exception as e:
        LOGGER.error(f"/link error: {e}")
        await message.reply_text(f"❌ ᴇʀʀᴏʀ: <code>{e}</code>")


@Client.on_message(filters.command("batch") & filters.user(ADMINS))
async def batch_cmd(client, message):
    """
    Usage: /batch <first_message_link> <last_message_link>
    Generates shareable links for each message in the range from the
    BIN_CHANNEL.
    """
    if len(message.command) < 3:
        return await message.reply_text(
            "ᴜꜱᴀɢᴇ:\n<code>/batch &lt;first_msg_link&gt; &lt;last_msg_link&gt;</code>"
        )

    def parse(link: str):
        m = re.match(r"https?://t\.me/(?:c/)?([^/]+)/(\d+)", link.strip())
        if not m:
            return None, None
        return m.group(1), int(m.group(2))

    _, start_id = parse(message.command[1])
    _, end_id = parse(message.command[2])
    if not start_id or not end_id:
        return await message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴍᴇꜱꜱᴀɢᴇ ʟɪɴᴋꜱ.")
    if start_id > end_id:
        start_id, end_id = end_id, start_id
    if end_id - start_id > 200:
        return await message.reply_text("❌ ᴍᴀx 200 ꜰɪʟᴇꜱ ᴀᴛ ᴀ ᴛɪᴍᴇ.")

    status = await message.reply_text("⏳ ɢᴇɴᴇʀᴀᴛɪɴɢ ʟɪɴᴋꜱ…")
    bot_username = (await client.get_me()).username
    links = []
    failed = 0
    for mid in range(start_id, end_id + 1):
        try:
            msg = await client.get_messages(BIN_CHANNEL, mid)
            if not msg or not msg.media:
                failed += 1
                continue
            encoded = _encode_file(msg.id)
            links.append(f"https://t.me/{bot_username}?start={encoded}")
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    if not links:
        return await status.edit_text("❌ ɴᴏ ᴍᴇᴅɪᴀ ᴍᴇꜱꜱᴀɢᴇꜱ ꜰᴏᴜɴᴅ ɪɴ ᴛʜᴀᴛ ʀᴀɴɢᴇ.")

    text = f"✅ <b>{len(links)} ʟɪɴᴋꜱ ɢᴇɴᴇʀᴀᴛᴇᴅ</b> ({failed} ꜰᴀɪʟᴇᴅ):\n\n" + "\n".join(links)
    if len(text) <= 4000:
        await status.edit_text(text, disable_web_page_preview=True)
    else:
        # Send as a file
        import io
        buf = io.BytesIO("\n".join(links).encode())
        buf.name = f"batch_{start_id}_{end_id}.txt"
        await message.reply_document(buf, caption=f"✅ {len(links)} links")
        await status.delete()


# ---------------------------------------------------------------------------
# /verification — count of users verified today
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("verification") & filters.user(ADMINS))
async def verification_cmd(client, message):
    count = await db.count_verified_users()
    await message.reply_text(
        f"<b>📊 ᴠᴇʀɪꜰɪᴇᴅ ᴜꜱᴇʀꜱ (ᴛᴏᴅᴀʏ):</b> <code>{count}</code>"
    )
