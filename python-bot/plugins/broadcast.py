import datetime
import time
import os
import asyncio
from logging_helper import LOGGER
from pyrogram import Client, filters, enums
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from pyrogram.errors import FloodWait
from database.users_chats_db import db
from info import ADMINS
from utils import users_broadcast, groups_broadcast, temp, get_readable_time, clear_junk, junk_group
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, target = query.data.split("#", 1)
    if target == 'users':
        temp.B_USERS_CANCEL = True
        await query.message.edit("🛑 ᴛʀʏɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ ᴜꜱᴇʀꜱ ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ...")
    elif target == 'groups':
        temp.B_GROUPS_CANCEL = True
        await query.message.edit("🛑 ᴛʀʏɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ ɢʀᴏᴜᴘꜱ ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ...")

BATCH_SIZE = 2000
broadcast_cache = {}

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_users(bot, message):
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")
    
    broadcast_cache[message.from_user.id] = {
        "message": message.reply_to_message
    }
    
    total_users = await db.total_users_count()
    total_batches = (total_users + BATCH_SIZE - 1) // BATCH_SIZE
    
    batch_buttons = []
    for i in range(total_batches):
        start = i * BATCH_SIZE + 1
        end = min((i + 1) * BATCH_SIZE, total_users)
        batch_buttons.append([
            InlineKeyboardButton(f"📦 Batch {i+1}: {start}-{end}", callback_data=f"bcast_batch#{i}")
        ])
    batch_buttons.append([InlineKeyboardButton("📢 All Users", callback_data="bcast_batch#all")])
    
    await message.reply(
        f"<b>📊 Total Users: {total_users}</b>\n"
        f"<b>📦 Batches: {total_batches} (2000 users each)</b>\n\n"
        f"Select which batch to broadcast:",
        reply_markup=InlineKeyboardMarkup(batch_buttons)
    )

@Client.on_callback_query(filters.regex(r'^bcast_batch#'))
async def broadcast_batch_select(bot, query):
    user_id = query.from_user.id
    if user_id not in ADMINS:
        return await query.answer("❌ Not authorized!", show_alert=True)
    
    if user_id not in broadcast_cache or "message" not in broadcast_cache[user_id]:
        return await query.answer("❌ Session expired. Use /broadcast again.", show_alert=True)
    
    _, batch_id = query.data.split("#", 1)
    broadcast_cache[user_id]["batch"] = batch_id
    
    await query.message.edit(
        "<b>📌 Do you want to pin this message?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="bcast_pin#yes"),
             InlineKeyboardButton("❌ No", callback_data="bcast_pin#no")]
        ])
    )

@Client.on_callback_query(filters.regex(r'^bcast_pin#'))
async def broadcast_pin_select(bot, query):
    user_id = query.from_user.id
    if user_id not in ADMINS:
        return await query.answer("❌ Not authorized!", show_alert=True)
    
    if user_id not in broadcast_cache:
        return await query.answer("❌ Session expired. Use /broadcast again.", show_alert=True)
    
    if lock.locked():
        return await query.answer("⚠️ Another broadcast in progress!", show_alert=True)
    
    _, pin_choice = query.data.split("#", 1)
    is_pin = pin_choice == "yes"
    cached = broadcast_cache.pop(user_id)
    batch_id = cached["batch"]
    b_msg = cached["message"]
    
    total_users = await db.total_users_count()
    
    if batch_id == "all":
        start_idx = 0
        end_idx = total_users
        batch_label = "All Users"
    else:
        batch_num = int(batch_id)
        start_idx = batch_num * BATCH_SIZE
        end_idx = min((batch_num + 1) * BATCH_SIZE, total_users)
        batch_label = f"Batch {batch_num + 1} ({start_idx + 1}-{end_idx})"
    
    await query.message.delete()
    silentxbotz_status_msg = await bot.send_message(
        query.message.chat.id,
        f"📤 <b>Broadcasting to {batch_label}...</b>"
    )
    
    success = blocked = deleted = failed = done = 0
    start_time = time.time()
    cancelled = False
    current_idx = 0

    async def send_single(uid):
        try:
            _, result = await asyncio.wait_for(
                users_broadcast(uid, b_msg, is_pin),
                timeout=10
            )
            return result
        except asyncio.TimeoutError:
            return "Error"
        except Exception as e:
            LOGGER.error(f"Error sending broadcast to {uid}: {e}")
            return "Error"

    async with lock:
        users_cursor = await db.get_all_users()
        batch = []
        async for user in users_cursor:
            if current_idx < start_idx:
                current_idx += 1
                continue
            if current_idx >= end_idx:
                break
            
            if temp.B_USERS_CANCEL:
                temp.B_USERS_CANCEL = False
                cancelled = True
                break
            
            batch.append(int(user["id"]))
            current_idx += 1
            
            if len(batch) >= 20:
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*[send_single(uid) for uid in batch], return_exceptions=True),
                        timeout=60
                    )
                    for res in results:
                        if isinstance(res, Exception):
                            failed += 1
                        elif res == "Success":
                            success += 1
                        elif res == "Blocked":
                            blocked += 1
                        elif res == "Deleted":
                            deleted += 1
                        else:
                            failed += 1
                except asyncio.TimeoutError:
                    failed += len(batch)
                    LOGGER.error(f"Batch timeout at {done}")
                except Exception as e:
                    failed += len(batch)
                    LOGGER.error(f"Batch error: {e}")
                
                done += len(batch)
                batch = []
                
                if done % 100 == 0:
                    elapsed = get_readable_time(time.time() - start_time)
                    try:
                        await silentxbotz_status_msg.edit(
                            f"📣 <b>Broadcast Progress ({batch_label}):</b>\n\n"
                            f"👥 Target: <code>{end_idx - start_idx}</code>\n"
                            f"✅ Done: <code>{done}</code>\n"
                            f"📬 Success: <code>{success}</code>\n"
                            f"⛔ Blocked: <code>{blocked}</code>\n"
                            f"🗑️ Deleted: <code>{deleted}</code>\n"
                            f"⏱️ Time: {elapsed}",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#users")]
                            ])
                        )
                    except Exception:
                        pass
                await asyncio.sleep(1.5)
        
        if batch and not cancelled:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[send_single(uid) for uid in batch], return_exceptions=True),
                    timeout=60
                )
                for res in results:
                    if isinstance(res, Exception):
                        failed += 1
                    elif res == "Success":
                        success += 1
                    elif res == "Blocked":
                        blocked += 1
                    elif res == "Deleted":
                        deleted += 1
                    else:
                        failed += 1
            except Exception:
                failed += len(batch)
            done += len(batch)

    elapsed = get_readable_time(time.time() - start_time)
    final_status = (
        f"{'❌ <b>Broadcast Cancelled.</b>' if cancelled else '✅ <b>Broadcast Completed.</b>'}\n\n"
        f"📦 {batch_label}\n"
        f"🕒 Time: {elapsed}\n"
        f"👥 Target: <code>{end_idx - start_idx}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"⛔ Blocked: <code>{blocked}</code>\n"
        f"🗑️ Deleted: <code>{deleted}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    await silentxbotz_status_msg.edit(final_status)


grp_broadcast_cache = {}

@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_group(bot, message):
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")
    b_msg = message.reply_to_message
    grp_broadcast_cache[message.from_user.id] = {
        "message": b_msg,
        "chat_id": message.chat.id
    }
    await message.reply(
        "<b>📢 Group Broadcast</b>\n\nDo you want to pin this message in groups?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Yes, Pin it", callback_data="grp_bcast_pin#yes"),
             InlineKeyboardButton("❌ No", callback_data="grp_bcast_pin#no")]
        ])
    )

@Client.on_callback_query(filters.regex(r'^grp_bcast_pin'))
async def grp_broadcast_pin_callback(bot, query):
    user_id = query.from_user.id
    if user_id not in ADMINS:
        return await query.answer("❌ You are not authorized!", show_alert=True)
    if user_id not in grp_broadcast_cache:
        return await query.answer("❌ Session expired. Please use /grp_broadcast again.", show_alert=True)

    _, choice = query.data.split("#", 1)
    is_pin = choice == "yes"
    cached = grp_broadcast_cache.pop(user_id)
    b_msg = cached["message"]

    await query.message.delete()
    chats = await db.get_all_chats()
    total_chats = await db.total_chat_count()
    silentxbotz_status_msg = await bot.send_message(cached["chat_id"], "📤 <b>Broadcasting your message to groups...</b>")
    start_time = time.time()
    done = success = failed = skipped = 0
    cancelled = False

    async with lock:
        async for chat in chats:
            if temp.B_GROUPS_CANCEL:
                temp.B_GROUPS_CANCEL = False
                cancelled = True
                break
            try:
                member = await bot.get_chat_member(int(chat['id']), bot.me.id)
                if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                    skipped += 1
                    done += 1
                    continue
                sts = await groups_broadcast(int(chat['id']), b_msg, is_pin)
            except Exception as e:
                LOGGER.error(f"Error broadcasting to group {chat['id']}: {e}")
                sts = 'Error'
            if sts == "Success":
                success += 1
            else:
                failed += 1
            done += 1
            if done % 10 == 0:
                try:
                    btn = [[InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#groups")]]
                    await silentxbotz_status_msg.edit(
                        f"📣 <b>Group broadcast progress:</b>\n\n"
                        f"👥 Total Groups: <code>{total_chats}</code>\n"
                        f"✅ Completed: <code>{done} / {total_chats}</code>\n"
                        f"📬 Success: <code>{success}</code>\n"
                        f"⏭️ Skipped (not admin): <code>{skipped}</code>\n"
                        f"❌ Failed: <code>{failed}</code>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.5)
    time_taken = get_readable_time(time.time() - start_time)
    silentxbotz_text = (
        f"{'❌ <b>Groups broadcast cancelled!</b>' if cancelled else '✅ <b>Group broadcast completed.</b>'}\n"
        f"⏱️ Completed in {time_taken}\n\n"
        f"👥 Total Groups: <code>{total_chats}</code>\n"
        f"✅ Completed: <code>{done} / {total_chats}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"⏭️ Skipped (not admin): <code>{skipped}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    try:
        await silentxbotz_status_msg.edit(silentxbotz_text)
    except MessageTooLong:
        with open("reason.txt", "w+") as outfile:
            outfile.write(str(failed))
        await message.reply_document(
            "reason.txt", caption=silentxbotz_text
        )
        os.remove("reason.txt")

@Client.on_message(filters.command("clear_junk") & filters.user(ADMINS))
async def remove_junkuser__db(bot, message):
    users = await db.get_all_users()
    b_msg = message 
    sts = await message.reply_text('ɪɴ ᴘʀᴏɢʀᴇss.... ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ')   
    start_time = time.time()
    total_users = await db.total_users_count()
    blocked = 0
    deleted = 0
    failed = 0
    done = 0
    async for user in users:
        pti, sh = await clear_junk(int(user['id']), b_msg)
        if pti == False:
            if sh == "Blocked":
                blocked+=1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        if not done % 50:
            await sts.edit(f"In Progress:\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")    
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    await sts.delete()
    await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")

@Client.on_message(filters.command(["junk_group", "clear_junk_group"]) & filters.user(ADMINS))
async def junk_clear_group(bot, message):
    groups = await db.get_all_chats()
    if not groups:
        grp = await message.reply_text("❌ Nᴏ ɢʀᴏᴜᴘs ғᴏᴜɴᴅ ғᴏʀ ᴄʟᴇᴀʀ Jᴜɴᴋ ɢʀᴏᴜᴘs.")
        await asyncio.sleep(60)
        await grp.delete()
        return
    b_msg = message
    sts = await message.reply_text(text='..............')
    start_time = time.time()
    total_groups = await db.total_chat_count()
    done = 0
    failed = ""
    deleted = 0
    async for group in groups:
        pti, sh, ex = await junk_group(int(group['id']), b_msg)        
        if pti == False:
            if sh == "deleted":
                deleted+=1 
                failed += ex 
                try:
                    await bot.leave_chat(int(group['id']))
                except Exception as e:
                    print(f"{e} > {group['id']}")  
        done += 1
        if not done % 50:
            await sts.edit(f"in progress:\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")    
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    await sts.delete()
    try:
        await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}\n\nFiled Reson:- {failed}")    
    except MessageTooLong:
        with open('junk.txt', 'w+') as outfile:
            outfile.write(failed)
        await message.reply_document('junk.txt', caption=f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")
        os.remove("junk.txt")
