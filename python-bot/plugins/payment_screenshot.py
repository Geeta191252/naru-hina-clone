"""
Payment Screenshot Forwarder
----------------------------
Jab koi user bot ke private DM mein photo (payment screenshot) bhejta hai,
to ye plugin automatically wo screenshot ADMINS ko forward kar deta hai
saath mein user ki details (name, id, username) ke saath.
"""

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from info import ADMINS, PREMIUM_LOGS
from logging_helper import LOGGER


@Client.on_message(filters.private & filters.photo & ~filters.user(ADMINS))
async def forward_payment_screenshot(client: Client, message: Message):
    """Forward any photo sent in bot DM to all ADMINS as a payment screenshot."""
    try:
        user = message.from_user
        if not user:
            return

        # Only forward if caption contains payment-related keyword
        caption_text = (message.caption or "").lower()
        keywords = ["payment", "paid", "upi", "paytm", "gpay", "phonepe"]
        if not any(k in caption_text for k in keywords):
            return

        username = f"@{user.username}" if user.username else "ɴᴏ ᴜꜱᴇʀɴᴀᴍᴇ"
        full_name = user.first_name or ""
        if user.last_name:
            full_name += f" {user.last_name}"

        caption = (
            f"💸 <b>ɴᴇᴡ ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ʀᴇᴄᴇɪᴠᴇᴅ</b>\n\n"
            f"👤 <b>ɴᴀᴍᴇ:</b> {full_name}\n"
            f"🆔 <b>ᴜꜱᴇʀ ɪᴅ:</b> <code>{user.id}</code>\n"
            f"🔗 <b>ᴜꜱᴇʀɴᴀᴍᴇ:</b> {username}\n"
            f"💬 <b>ᴍᴇɴᴛɪᴏɴ:</b> {user.mention}\n\n"
            f"⚡ ᴀᴄᴛɪᴠᴀᴛᴇ ᴘʀᴇᴍɪᴜᴍ:\n"
            f"<code>/add_premium {user.id} 1 month</code>"
        )

        reply_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 ʀᴇᴘʟʏ ᴜꜱᴇʀ", url=f"tg://user?id={user.id}")
        ]])

        # Send to every admin in DM
        for admin_id in ADMINS:
            try:
                await message.copy(
                    chat_id=int(admin_id),
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_btn,
                )
            except Exception as e:
                LOGGER.error(f"Failed to forward screenshot to admin {admin_id}: {e}")

        # Also log to premium logs channel (best effort)
        try:
            await message.copy(
                chat_id=PREMIUM_LOGS,
                caption=caption,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            LOGGER.error(f"Failed to forward screenshot to PREMIUM_LOGS: {e}")

        # Acknowledge to user
        await message.reply_text(
            "<b>✅ ᴀᴀᴘᴋᴀ ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ᴀᴅᴍɪɴ ᴋᴏ ʙʜᴇᴊ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ.\n\n"
            "⏳ ᴋʀɪᴘʏᴀ ᴋᴜᴄʜ ꜱᴀᴍᴀʏ ᴡᴀɪᴛ ᴋᴀʀᴇɴ — ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴋᴇ ʙᴀᴀᴅ ᴀᴀᴘᴋᴀ ᴘʀᴇᴍɪᴜᴍ ɪɴꜱᴛᴀɴᴛ ᴀᴄᴛɪᴠᴀᴛᴇ ʜᴏ ᴊᴀᴀᴇɢᴀ.\n\n"
            "💬 ᴀɢᴀʀ ᴊᴀʟᴅɪ ᴄʜᴀʜɪᴇ ᴛᴏ ᴀᴅᴍɪɴ ᴋᴏ ᴅᴍ ᴋᴀʀᴇɴ — @Hidden_Xman</b>",
            quote=True,
        )
    except Exception as e:
        LOGGER.error(f"Error in forward_payment_screenshot: {e}")
