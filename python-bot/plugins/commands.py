import os
import re, sys
import json
import base64
import random
import asyncio
import time
import pytz
from logging_helper import LOGGER
from .pm_filter import auto_filter 
from Script import script
from datetime import datetime
from database.refer import referdb
from database.topdb import silentdb
from pyrogram.enums import ParseMode, ChatType
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import *
from database.ia_filterdb import *
from database.users_chats_db import db
from info import *
from utils import *

TIMEZONE = "Asia/Kolkata"
BATCH_FILES = {}

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    bot_id = client.me.id
    if EMOJI_MODE:
        try:
            await message.react(emoji=random.choice(REACTIONS))
        except Exception:
            pass
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    m = message
    if len(m.command) == 2 and m.command[1].startswith(('notcopy', 'sendall')):
        _, userid, verify_id, file_id = m.command[1].split("_", 3)
        user_id = int(userid)
        grp_id = temp.VERIFICATIONS.get(user_id, 0)
        settings = await get_settings(grp_id)         
        verify_id_info = await db.get_verify_id_info(user_id, verify_id)
        if not verify_id_info or verify_id_info["verified"]:
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪɴ...</b>")
            return
        if USE_MINIAPP:
            mini = await db.get_miniapp_token(verify_id)
            if not mini or not mini.get("verified"):
                await message.reply("<b>❌ ᴀᴅꜱ ɴᴏᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ. ᴘʟᴇᴀꜱᴇ ᴡᴀᴛᴄʜ ᴀʟʟ ᴀᴅꜱ ɪɴ ᴛʜᴇ ᴍɪɴɪ ᴀᴘᴘ.</b>")
                return
        ist_timezone = pytz.timezone('Asia/Kolkata')
        if await db.user_verified(user_id):
            key = "third_time_verified"
        else:
            key = "second_time_verified" if await db.is_user_verified(user_id) else "last_verified"
        current_time = datetime.now(tz=ist_timezone)
        result = await db.update_notcopy_user(user_id, {key:current_time})
        await db.update_verify_id_info(user_id, verify_id, {"verified":True})
        if key == "third_time_verified": 
            num = 3 
        else: 
            num =  2 if key == "second_time_verified" else 1 
        if key == "third_time_verified": 
            msg = script.THIRDT_VERIFY_COMPLETE_TEXT
        else:
            msg = script.SECOND_VERIFY_COMPLETE_TEXT if key == "second_time_verified" else script.VERIFY_COMPLETE_TEXT
        if USE_MINIAPP:
            verifiedfiles = f"https://telegram.me/{temp.U_NAME}?start=unlocked_{verify_id}"
        elif message.command[1].startswith('sendall'):
            verifiedfiles = f"https://telegram.me/{temp.U_NAME}?start=allfiles_{grp_id}_{file_id}"
        else:
            verifiedfiles = f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}"
        try:
            log_chat_id = settings.get('log') or LOG_VR_CHANNEL or LOG_CHANNEL
            await client.send_message(log_chat_id, script.VERIFIED_LOG_TEXT.format(m.from_user.mention, user_id, datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %B %Y'), num))
        except Exception as e:
            LOGGER.error(f"Verification log send failed, continuing file unlock: {e}")
        btn = [[
            InlineKeyboardButton("✅ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ꜰɪʟᴇ ✅", url=verifiedfiles),
        ]]
        reply_markup=InlineKeyboardMarkup(btn)
        dlt=await m.reply_photo(
            photo=(VERIFY_IMG),
            caption=msg.format(message.from_user.mention, get_readable_time(TWO_VERIFY_GAP)),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        await asyncio.sleep(300)
        await dlt.delete()
        return         
    unlocked_data = None
    if len(m.command) == 2 and m.command[1].startswith('unlocked_'):
        verify_id = m.command[1].split("_", 1)[1]
        mini = await db.get_miniapp_token(verify_id)
        if not mini or not mini.get("verified") or int(mini.get("user_id", 0)) != message.from_user.id:
            await message.reply("<b>❌ ᴀᴅꜱ ɴᴏᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ. ᴘʟᴇᴀꜱᴇ ᴡᴀᴛᴄʜ ᴀʟʟ ᴀᴅꜱ ɪɴ ᴛʜᴇ ᴍɪɴɪ ᴀᴘᴘ.</b>")
            return
        grp_id = int(mini.get("grp_id", 0))
        file_id = mini.get("file_id")
        unlocked_data = f"allfiles_{grp_id}_{file_id}" if mini.get("kind") == "sendall" else f"file_{grp_id}_{file_id}"
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        silenxbotz=await message.reply_sticker("CAACAgEAAxkBAAENpaZnl898tVVOj-69IH89gx-8ee-CCAACWwIAAu8vQEXX2jgCrI2F-jYE")
        await asyncio.sleep(5)
        await silenxbotz.delete()
        if not await db.get_chat(message.chat.id):
            total=await client.get_chat_members_count(message.chat.id)
            await client.send_message(LOG_CHANNEL, script.LOG_TEXT_G.format(message.chat.title, message.chat.id, total, "Unknown"))       
            await db.add_chat(message.chat.id, message.chat.title)
        return 
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(message.from_user.id, message.from_user.mention))
    if len(message.command) != 2:
        buttons = [[
                    InlineKeyboardButton('+ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ +', url=f'http://telegram.me/{temp.U_NAME}?startgroup=true')
                ],[
                    InlineKeyboardButton('ᴛʀᴇɴᴅɪɴɢ', callback_data="topsearch"),
                    InlineKeyboardButton('ᴜᴘɢʀᴀᴅᴇ', callback_data="premium"),
                ],[
                    InlineKeyboardButton('ᴅɪꜱᴄʟᴀɪᴍᴇʀ', callback_data='disclaimer'),
                    InlineKeyboardButton('ᴀʙᴏᴜᴛ', callback_data='me')
                ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        return
        
    if message.command[1].startswith("reff_"):
        try:
            user_id = int(message.command[1].split("_")[1])
        except ValueError:
            await message.reply_text("Invalid refer!")
            return
        if user_id == message.from_user.id:
            await message.reply_text("Hᴇʏ Dᴜᴅᴇ, Yᴏᴜ Cᴀɴ'ᴛ Rᴇғᴇʀ Yᴏᴜʀsᴇʟғ 🤣!\n\nsʜᴀʀᴇ ʟɪɴᴋ ʏᴏᴜʀ ғʀɪᴇɴᴅ ᴀɴᴅ ɢᴇᴛ 10 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛ ɪғ ʏᴏᴜ ᴀʀᴇ ᴄᴏʟʟᴇᴄᴛɪɴɢ 100 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛs ᴛʜᴇɴ ʏᴏᴜ ᴄᴀɴ ɢᴇᴛ 1 ᴍᴏɴᴛʜ ғʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ ᴍᴇᴍʙᴇʀsʜɪᴘ.")
            return
        if referdb.is_user_in_list(message.from_user.id):
            await message.reply_text("Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴀʟʀᴇᴀᴅʏ ɪɴᴠɪᴛᴇᴅ ❗")
            return
        if await db.is_user_exist(message.from_user.id): 
            await message.reply_text("‼️ Yᴏᴜ Hᴀᴠᴇ Bᴇᴇɴ Aʟʀᴇᴀᴅʏ Iɴᴠɪᴛᴇᴅ ᴏʀ Jᴏɪɴᴇᴅ")
            return 
        try:
            uss = await client.get_users(user_id)
        except Exception:
            return          
        referdb.add_user(message.from_user.id)
        fromuse = referdb.get_refer_points(user_id) + 10
        if fromuse == 100:
            referdb.add_refer_points(user_id, 0) 
            await message.reply_text(f"🎉 𝗖𝗼𝗻𝗴𝗿𝗮𝘁𝘂𝗹𝗮𝘁𝗶𝗼𝗻𝘀! 𝗬𝗼𝘂 𝘄𝗼𝗻 𝟭𝟬 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗽𝗼𝗶𝗻𝘁 𝗯𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂 𝗵𝗮𝘃𝗲 𝗯𝗲𝗲𝗻 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗜𝗻𝘃𝗶𝘁𝗲𝗱 ☞ {uss.mention}!")                   
            await message.reply_text(user_id, f"You have been successfully invited by {message.from_user.mention}!")    
            seconds = 2592000
            if seconds > 0:
                expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
                user_data = {"id": user_id, "expiry_time": expiry_time}
                await db.update_user(user_data)             
                await client.send_message(
                chat_id=user_id,
                text=f"<b>Hᴇʏ {uss.mention}\n\nYᴏᴜ ɢᴏᴛ 1 ᴍᴏɴᴛʜ ᴘʀᴇᴍɪᴜᴍ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʙʏ ɪɴᴠɪᴛɪɴɢ 10 ᴜsᴇʀs ❗", disable_web_page_preview=True              
                )
            for admin in ADMINS:
                await client.send_message(chat_id=admin, text=f"Sᴜᴄᴄᴇss ғᴜʟʟʏ ᴛᴀsᴋ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ʙʏ ᴛʜɪs ᴜsᴇʀ:\n\nuser Nᴀᴍᴇ: {uss.mention}\n\nUsᴇʀ ɪᴅ: {uss.id}!")  
        else:
            referdb.add_refer_points(user_id, fromuse)
            await message.reply_text(f"You have been successfully invited by {uss.mention}!")
            await client.send_message(user_id, f"𝗖𝗼𝗻𝗴𝗿𝗮𝘁𝘂𝗹𝗮𝘁𝗶𝗼𝗻𝘀! 𝗬𝗼𝘂 𝘄𝗼𝗻 𝟭𝟬 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗽𝗼𝗶𝗻𝘁 𝗯𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂 𝗵𝗮𝘃𝗲 𝗯𝗲𝗲𝗻 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗜𝗻𝘃𝗶𝘁𝗲𝗱 ☞{message.from_user.mention}!")
        return
        
        
    if len(message.command) == 2 and message.command[1].startswith('getfile'):
        movies = message.command[1].split("-", 1)[1] 
        movie = movies.replace('-',' ')
        message.text = movie 
        await auto_filter(client, message) 
        return
            
    data = unlocked_data or message.command[1]
    try:
        pre, grp_id, file_id = data.split('_', 2)
    except:
        pre, grp_id, file_id = "", 0, data

    try:
        settings = await get_settings(int(data.split("_", 2)[1]))
        fsub_id_list = settings.get('fsub_id', [])
        btn = []
        i = 1
        fsub_id_list = fsub_id_list + AUTH_CHANNEL if AUTH_CHANNEL else fsub_id_list
        fsub_id_list = fsub_id_list + AUTH_REQ_CHANNEL if AUTH_REQ_CHANNEL else fsub_id_list
        
        if fsub_id_list:
            fsub_ids = []
            for chnl in fsub_id_list:
                if chnl not in fsub_ids:
                    fsub_ids.append(chnl)
                else:
                    continue
                try:
                    channel_name = (await client.get_chat(chnl)).title or f"Update Channel"
                except Exception:
                    channel_name = f"Update Channel"
                if AUTH_REQ_CHANNEL and chnl in AUTH_REQ_CHANNEL and not await is_req_subscribed(client, message, chnl):
                    try:
                        invite_link = await client.create_chat_invite_link(chnl, creates_join_request=True)
                    except ChatAdminRequired:
                        LOGGER.error("Bot Ko AUTH_CHANNEL Per Admin Bana Bhai Pahile 🤧")
                        return
                    btn.append([
                        InlineKeyboardButton(f"🌹 {i}. {channel_name} 🌿", url=invite_link.invite_link)
                    ])
                elif chnl not in AUTH_REQ_CHANNEL and not await is_subscribed(client, message.from_user.id, chnl):
                    try:
                        invite_link = await client.create_chat_invite_link(chnl)
                    except ChatAdminRequired:
                        LOGGER.error("Bot Ko AUTH_CHANNEL Per Admin Bana Bhai Pahile 🤧")
                        return
                    btn.append([
                        InlineKeyboardButton(f"🌹 {i}. {channel_name} 🌿", url=invite_link.invite_link)
                    ])
                i += 1

            if btn:
                if message.command[1] != "subscribe":
                    btn.append([InlineKeyboardButton(" ᴛʀʏ ᴀɢᴀɪɴ 🌿", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
                await client.send_photo(
                    chat_id=message.from_user.id,
                    photo=random.choice(FSUB_IMG),
                    caption=script.FORCESUB_TEXT,
                    reply_markup=InlineKeyboardMarkup(btn),
                    parse_mode=enums.ParseMode.HTML,
                )
                return
    except Exception as e:
        await log_error(client, f"Got Error In Force Subscription Function.\n\n Error - {e}")
        LOGGER.error(f"Error In Fsub :- {e}")
        
    user_id = m.from_user.id
    if not unlocked_data and not await db.has_premium_access(user_id):
        try:
            grp_id = int(grp_id)
            user_verified = await db.is_user_verified(user_id)
            settings = await get_settings(grp_id)
            is_second_shortener = await db.use_second_shortener(user_id, settings.get('verify_time', TWO_VERIFY_GAP)) 
            is_third_shortener = await db.use_third_shortener(user_id, settings.get('third_verify_time', THREE_VERIFY_GAP))
            # When Mini App ads mode is on, ALWAYS show ads on every file request (no caching)
            force_ads = USE_MINIAPP and settings.get("is_verify", IS_VERIFY)
            if force_ads or (settings.get("is_verify", IS_VERIFY) and (not user_verified or is_second_shortener or is_third_shortener)):                
                verify_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
                await db.create_verify_id(user_id, verify_id)
                temp.VERIFICATIONS[user_id] = grp_id
                kind = 'sendall' if message.command[1].startswith('allfiles') else 'notcopy'
                if USE_MINIAPP:
                    # Monetag Mini App flow (ads inside Telegram WebApp, not browser)
                    await db.create_miniapp_token(verify_id, user_id, grp_id, file_id, kind, MINIAPP_TOKEN_EXPIRY)
                    verify = f"{URL.rstrip('/')}/miniapp/{verify_id}"
                else:
                    if kind == 'sendall':
                        verify = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=sendall_{user_id}_{verify_id}_{file_id}", grp_id, is_second_shortener, is_third_shortener)
                    else:
                        verify = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=notcopy_{user_id}_{verify_id}_{file_id}", grp_id, is_second_shortener, is_third_shortener)
                if is_third_shortener:
                    howtodownload = settings.get('tutorial_3', TUTORIAL_3)
                else:
                    howtodownload = settings.get('tutorial_2', TUTORIAL_2) if is_second_shortener else settings.get('tutorial', TUTORIAL)
                verify_btn_text = "🎬 ᴡᴀᴛᴄʜ ᴀᴅꜱ & ɢᴇᴛ ꜰɪʟᴇ 🎬" if USE_MINIAPP else "♻️ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴠᴇʀɪꜰʏ ♻️"
                if USE_MINIAPP:
                    # web_app button => opens INSIDE Telegram (no browser/Google)
                    verify_button = InlineKeyboardButton(text=verify_btn_text, web_app=WebAppInfo(url=verify))
                else:
                    verify_button = InlineKeyboardButton(text=verify_btn_text, url=verify)
                buttons = [[
                    verify_button
                ],[
                    InlineKeyboardButton(text="⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪꜰʏ ⁉️", url=howtodownload)
                ]]
                reply_markup=InlineKeyboardMarkup(buttons)
                if await db.user_verified(user_id): 
                    msg = script.THIRDT_VERIFICATION_TEXT
                else:            
                    msg = script.SECOND_VERIFICATION_TEXT if is_second_shortener else script.VERIFICATION_TEXT
                n=await m.reply_text(
                    text=msg.format(message.from_user.mention),
                    protect_content = True,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML
                )
                await asyncio.sleep(300) 
                await n.delete()
                await m.delete()
                return
        except Exception as e:
            await log_error(client, f"Got Error In Verification Funtion.\n\n Error - {e}")
            LOGGER.error(f"Error In Verification - {e}")
            pass
    
    if data.startswith("allfiles"):
        files = temp.GETALL.get(file_id)
        if not files:
            return await message.reply('<b><i>ɴᴏ ꜱᴜᴄʜ ꜰɪʟᴇ ᴇxɪꜱᴛꜱ !</b></i>')
        filesarr = []
        for file in files:
            file_id = file.file_id
            files_ = await get_file_details(file_id)
            files1 = files_[0]
            title = clean_filename(files1.file_name) 
            size = get_size(files1.file_size)
            f_caption = files1.caption
            settings = await get_settings(int(grp_id))
            SILENTX_CAPTION = settings.get('caption', CUSTOM_FILE_CAPTION)
            if SILENTX_CAPTION:
                try:
                    f_caption=SILENTX_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
                except Exception as e:
                    logger.exception(e)
                    f_caption = f_caption
            if f_caption is None:
                f_caption = clean_filename(files1.file_name) 
            if STREAM_MODE:
                btn = [
                    [InlineKeyboardButton('𝖦𝖾𝗇𝖾𝗋𝖺𝗍𝖾 𝖲𝗍𝗋𝖾𝗆𝗂𝗇𝗀 𝖫𝗂𝗇𝗄', callback_data=f'streamfile:{file_id}')],
                    [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]  
                ]
            else:
                btn = [
                    [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]
                ]
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                caption=f_caption,
                protect_content=settings.get('file_secure', PROTECT_CONTENT),
                reply_markup=InlineKeyboardMarkup(btn)
            )
            filesarr.append(msg)
        k = await client.send_message(chat_id=message.from_user.id, text=f"<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nᴛʜɪꜱ ᴍᴏᴠɪᴇ ꜰɪʟᴇ/ᴠɪᴅᴇᴏ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b><u><code>{get_time(DELETE_TIME)}</code></u> 🫥 <i></b>(ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪꜱꜱᴜᴇꜱ)</i>.\n\n<b><i>ᴘʟᴇᴀꜱᴇ ꜰᴏʀᴡᴀʀᴅ ᴛʜɪꜱ ꜰɪʟᴇ ᴛᴏ ꜱᴏᴍᴇᴡʜᴇʀᴇ ᴇʟꜱᴇ ᴀɴᴅ ꜱᴛᴀʀᴛ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ</i></b>")
        await asyncio.sleep(DELETE_TIME)
        for x in filesarr:
            await x.delete()
        await k.edit_text("<b>ʏᴏᴜʀ ᴀʟʟ ᴠɪᴅᴇᴏꜱ/ꜰɪʟᴇꜱ ᴀʀᴇ ᴅᴇʟᴇᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ !\nᴋɪɴᴅʟʏ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ</b>")
        return

    user = message.from_user.id
    files_ = await get_file_details(file_id)  
    settings = await get_settings(int(grp_id))
    if not files_:
        pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
        try:
            if STREAM_MODE:
                btn = [
                    [InlineKeyboardButton('𝖦𝖾𝗇𝖾𝗋𝖺𝗍𝖾 𝖲𝗍𝗋𝖾𝗆𝗂𝗇𝗀 𝖫𝗂𝗇𝗄', callback_data=f'streamfile:{file_id}')],
                    [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]
             
                ]
            else:
                btn = [
                    [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]
                ]
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                protect_content=settings.get('file_secure', PROTECT_CONTENT),
                reply_markup=InlineKeyboardMarkup(btn))

            filetype = msg.media
            file = getattr(msg, filetype.value)
            title = clean_filename(file.file_name)              
            size=get_size(file.file_size)
            f_caption = f"<code>{title}</code>"
            settings = await get_settings(int(grp_id))
            SILENTX_CAPTION = settings.get('caption', CUSTOM_FILE_CAPTION)
            if SILENTX_CAPTION:
                try:
                    f_caption=SILENTX_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='')
                except:
                    return
            await msg.edit_caption(f_caption)
            k = await msg.reply(f"<b>♻️ ᴛʜɪꜱ ꜰɪʟᴇ ᴡɪʟʟ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ {get_time(DELETE_TIME)}</b>", quote=True)
            await asyncio.sleep(DELETE_TIME)
            await msg.delete()
            await k.edit_text("<b>ʏᴏᴜʀ ᴠɪᴅᴇᴏ / ꜰɪʟᴇ ɪꜱ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ !!</b>")
            return
        except:
            pass
        return await message.reply('ɴᴏ ꜱᴜᴄʜ ꜰɪʟᴇ ᴇxɪꜱᴛꜱ !')
    
    files = files_[0]
    title = clean_filename(files.file_name)
    size = get_size(files.file_size)
    f_caption = files.caption
    settings = await get_settings(int(grp_id))            
    SILENTX_CAPTION = settings.get('caption', CUSTOM_FILE_CAPTION)
    if SILENTX_CAPTION:
        try:
            f_caption=SILENTX_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
        except Exception as e:
            LOGGER.error(e)
            f_caption = f_caption

    if f_caption is None:
        f_caption = clean_filename(files.file_name)
    if STREAM_MODE:
        btn = [
            [InlineKeyboardButton('𝖦𝖾𝗇𝖾𝗋𝖺𝗍𝖾 𝖲𝗍𝗋𝖾𝗆𝗂𝗇𝗀 𝖫𝗂𝗇𝗄', callback_data=f'streamfile:{file_id}')],
            [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]
        ]
    else:
        btn = [
            [InlineKeyboardButton('𝖴𝗉𝖽𝖺𝗍𝖾 𝖢𝗁𝖺𝗇𝗇𝖾𝗅', url=UPDATE_CHANNEL_LNK)]
        ]
    msg = await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=settings.get('file_secure', PROTECT_CONTENT),
        reply_markup=InlineKeyboardMarkup(btn)
    )
    k = await msg.reply(f"<b>♻️ ᴛʜɪꜱ ꜰɪʟᴇ ᴡɪʟʟ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ {get_time(DELETE_TIME)}</b>", quote=True)     
    await asyncio.sleep(DELETE_TIME)
    await msg.delete()
    await k.edit_text("<b>ʏᴏᴜʀ ᴠɪᴅᴇᴏ / ꜰɪʟᴇ ɪꜱ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ !!</b>")
    return

@Client.on_message(filters.command('logs') & filters.user(ADMINS))
async def log_file(bot, message):
    """Send log file"""
    try:
        await message.reply_document('TELEGRAM BOT.LOG')
    except Exception as e:
        await message.reply(str(e))


@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("Pʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        await message.reply('Rᴇᴘʟʏ ᴛᴏ ғɪʟᴇ ᴡɪᴛʜ /delete ᴡʜɪᴄʜ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ', quote=True)
        return
    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media:
            break
    else:
        await msg.edit('Tʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ғᴏʀᴍᴀᴛ')
        return    
    file_id, file_ref = unpack_new_file_id(media.file_id)
    result = await Media.collection.delete_one({'_id': file_id})
    if not result.deleted_count and MULTIPLE_DB:
        result = await Media2.collection.delete_one({'_id': file_id})
    if result.deleted_count:
        await msg.edit('Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ ✅')
        return
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    result = await Media.collection.delete_many({
        'file_name': file_name,
        'file_size': media.file_size,
        'mime_type': media.mime_type
    })
    if not result.deleted_count and MULTIPLE_DB:
        result = await Media2.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })
    if result.deleted_count:
        await msg.edit('Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ ✅')
        return
    result = await Media.collection.delete_many({
        'file_name': media.file_name,
        'file_size': media.file_size,
        'mime_type': media.mime_type
    })
    if not result.deleted_count and MULTIPLE_DB:
        result = await Media2.collection.delete_many({
            'file_name': media.file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })
    if result.deleted_count:
        await msg.edit('Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ ✅')
    else:
        await msg.edit('Fɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ ❌')


@Client.on_message(filters.command('deleteall') & filters.user(ADMINS))
async def delete_all_index(bot, message):
    await message.reply_text(
        'ᴛʜɪꜱ ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ʏᴏᴜʀ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇꜱ !\nᴅᴏ ʏᴏᴜ ꜱᴛɪʟʟ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ ?',
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="⚠️ ʏᴇꜱ ⚠️", callback_data="autofilter_delete"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ ɴᴏ ❌", callback_data="close_data"
                    )
                ],
            ]
        ),
        quote=True,
    )

@Client.on_callback_query(filters.regex(r'^autofilter_delete'))
async def delete_all_index_confirm(bot, message):
    await Media.collection.drop()
    if MULTIPLE_DB:    
        await Media2.collection.drop()
    await message.answer("Eᴠᴇʀʏᴛʜɪɴɢ's Gᴏɴᴇ")
    await message.message.edit('ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇꜱ ✅')

@Client.on_message(filters.command('settings'))
async def settings(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(f"ʏᴏᴜ'ʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")
    chat_type = message.chat.type
    if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        if not await is_check_admin(client, grp_id, message.from_user.id):
            return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
        await db.connect_group(grp_id, user_id)
        btn = [[
                InlineKeyboardButton(" ᴏᴘᴇɴ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ ", callback_data=f"opnsetpm#{grp_id}")
              ],[
                InlineKeyboardButton(" ᴏᴘᴇɴ ʜᴇʀᴇ ", callback_data=f"opnsetgrp#{grp_id}")
              ]]
        await message.reply_text(
                text="<b>ᴡʜᴇʀᴇ ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏᴘᴇɴ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ ? ⚙️</b>",
                reply_markup=InlineKeyboardMarkup(btn),
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=message.id
        )
    elif chat_type == enums.ChatType.PRIVATE:
        connected_groups = await db.get_connected_grps(user_id)
        if not connected_groups:
            return await message.reply_text("No Connected Groups Found .")
        group_list = []
        for group in connected_groups:
            try:
                silentx = await client.get_chat(group)
                group_list.append([
                    InlineKeyboardButton(text=silentx.title, callback_data=f"grp_pm#{silentx.id}")
                ])
            except Exception as e:
                LOGGER.error(f"Error In PM Settings Button - {e}")
                pass
        await message.reply_text('Here Is Your Connected Groups.', reply_markup=InlineKeyboardMarkup(group_list))
                                                                                                            

@Client.on_message(filters.command('reload'))
async def connect_group(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    user_id = message.from_user.id
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await db.connect_group(message.chat.id, user_id)
        await message.reply_text("Group Reloaded ✅ Now You Can Manage This Group From PM.")
    elif message.chat.type == enums.ChatType.PRIVATE:
        if len(message.command) < 2:
            await message.reply_text("Use: /reload <group_id>")
            return
        try:
            group_id = int(message.command[1])
            if not await is_check_admin(client, group_id, user_id):
                await message.reply_text("You're Not Admin In That Group.")
                return
            chat = await client.get_chat(group_id)
            await db.connect_group(group_id, user_id)
            await message.reply_text(f"Linked {chat.title} to PM.")
        except:
            await message.reply_text("Invalid group ID or error occurred.")

@Client.on_message((filters.command(["request", "Request"]) | filters.regex("#request") | filters.regex("#Request")) & filters.group)
async def requests(bot, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    if REQST_CHANNEL is None or SUPPORT_CHAT_ID is None: return # Must add REQST_CHANNEL and SUPPORT_CHAT_ID to use this feature
    if message.reply_to_message and SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.reply_to_message.text
        try:
            if REQST_CHANNEL is not None:
                btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.reply_to_message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                reported_post = await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.reply_to_message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                    reported_post = await bot.send_message(chat_id=admin, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>ʏᴏᴜ ᴍᴜꜱᴛ ᴛʏᴘᴇ ᴀʙᴏᴜᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ [ᴍɪɴɪᴍᴜᴍ 3 ᴄʜᴀʀᴀᴄᴛᴇʀꜱ]. ʀᴇǫᴜᴇꜱᴛꜱ ᴄᴀɴ'ᴛ ʙᴇ ᴇᴍᴘᴛʏ.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass
        
    elif SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.text
        keywords = ["#request", "/request", "#Request", "/Request"]
        for keyword in keywords:
            if keyword in content:
                content = content.replace(keyword, "")
        try:
            if REQST_CHANNEL is not None and len(content) >= 3:
                btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                reported_post = await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                    reported_post = await bot.send_message(chat_id=admin, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>ʏᴏᴜ ᴍᴜꜱᴛ ᴛʏᴘᴇ ᴀʙᴏᴜᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ [ᴍɪɴɪᴍᴜᴍ 3 ᴄʜᴀʀᴀᴄᴛᴇʀꜱ]. ʀᴇǫᴜᴇꜱᴛꜱ ᴄᴀɴ'ᴛ ʙᴇ ᴇᴍᴘᴛʏ.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass
    
    elif SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.text
        keywords = ["#request", "/request", "#Request", "/Request"]
        for keyword in keywords:
            if keyword in content:
                content = content.replace(keyword, "")
        try:
            if REQST_CHANNEL is not None and len(content) >= 3:
                btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                reported_post = await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{message.link}"),
                        InlineKeyboardButton('ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ', callback_data=f'show_option#{reporter}')
                      ]]
                    reported_post = await bot.send_message(chat_id=admin, text=f"<b>📝 ʀᴇǫᴜᴇꜱᴛ : <u>{content}</u>\n\n📚 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n📖 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : {reporter}\n\n</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>ʏᴏᴜ ᴍᴜꜱᴛ ᴛʏᴘᴇ ᴀʙᴏᴜᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ [ᴍɪɴɪᴍᴜᴍ 3 ᴄʜᴀʀᴀᴄᴛᴇʀꜱ]. ʀᴇǫᴜᴇꜱᴛꜱ ᴄᴀɴ'ᴛ ʙᴇ ᴇᴍᴘᴛʏ.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass
    else:
        success = False    
    if success:
        link = await bot.create_chat_invite_link(int(REQST_CHANNEL))
        btn = [[
                InlineKeyboardButton('ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=link.invite_link),
                InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ', url=f"{reported_post.link}")
              ]]
        await message.reply_text("<b>ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ʜᴀꜱ ʙᴇᴇɴ ᴀᴅᴅᴇᴅ! ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ ꜰᴏʀ ꜱᴏᴍᴇ ᴛɪᴍᴇ.\n\nᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ ꜰɪʀꜱᴛ & ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ.</b>", reply_markup=InlineKeyboardMarkup(btn))
    
@Client.on_message(filters.command("send") & filters.user(ADMINS))
async def send_msg(bot, message):
    if message.reply_to_message:
        target_id = message.text.split(" ", 1)[1]
        out = "Users Saved In DB Are:\n\n"
        success = False
        try:
            user = await bot.get_users(target_id)
            users = await db.get_all_users()
            async for usr in users:
                out += f"{usr['id']}"
                out += '\n'
            if str(user.id) in str(out):
                await message.reply_to_message.copy(int(user.id))
                success = True
            else:
                success = False
            if success:
                await message.reply_text(f"<b>ʏᴏᴜʀ ᴍᴇꜱꜱᴀɢᴇ ʜᴀꜱ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇɴᴛ ᴛᴏ {user.mention}.</b>")
            else:
                await message.reply_text("<b>ᴛʜɪꜱ ᴜꜱᴇʀ ᴅɪᴅɴ'ᴛ ꜱᴛᴀʀᴛᴇᴅ ᴛʜɪꜱ ʙᴏᴛ ʏᴇᴛ !</b>")
        except Exception as e:
            await message.reply_text(f"<b>Error: {e}</b>")
    else:
        await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴀꜱ ᴀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇꜱꜱᴀɢᴇ ᴜꜱɪɴɢ ᴛʜᴇ ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ ɪᴅ. ꜰᴏʀ ᴇɢ:  /send ᴜꜱᴇʀɪᴅ</b>")

@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot, message):
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, This command won't work in groups. It only works on my PM !</b>")
    else:
        pass
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, Give me a keyword along with the command to delete files.</b>")
    k = await bot.send_message(chat_id=message.chat.id, text=f"<b>Fetching Files for your query {keyword} on DB... Please wait...</b>")
    files, total = await get_bad_files(keyword)
    await k.delete()
    btn = [[
       InlineKeyboardButton("⚠️ Yes, Continue ! ⚠️", callback_data=f"killfilesdq#{keyword}")
       ],[
       InlineKeyboardButton("❌ No, Abort operation ! ❌", callback_data="close_data")
    ]]
    await message.reply_text(
        text=f"<b>Found {total} files for your query {keyword} !\n\nDo you want to delete?</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex("topsearch"))
async def topsearch_callback(client, callback_query):    
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))    
    limit = 20  
    top_messages = await silentdb.get_top_messages(limit)
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        msg_lower = msg.lower()
        if msg_lower not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg_lower)            
            if len(msg) > 35:
                truncated_messages.append(msg[:32] + "...")
            else:
                truncated_messages.append(msg)
    keyboard = [truncated_messages[i:i+2] for i in range(0, len(truncated_messages), 2)]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        one_time_keyboard=True, 
        resize_keyboard=True, 
        placeholder="Most searches of the day"
    )
    await callback_query.message.reply_text("<b>Tᴏᴘ Sᴇᴀʀᴄʜᴇs Oғ Tʜᴇ Dᴀʏ 👇</b>", reply_markup=reply_markup)
    await callback_query.answer()

@Client.on_message(filters.command('top_search'))
async def top(_, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))
    try:
        limit = int(message.command[1])
    except (IndexError, ValueError):
        limit = 20
    top_messages = await silentdb.get_top_messages(limit)
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        if msg.lower() not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg.lower())            
            if len(msg) > 35:
                truncated_messages.append(msg[:35 - 3])
            else:
                truncated_messages.append(msg)
    keyboard = []
    for i in range(0, len(truncated_messages), 2):
        row = truncated_messages[i:i+2]
        keyboard.append(row)
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True, placeholder="Most searches of the day")
    await message.reply_text(f"<b>Tᴏᴘ Sᴇᴀʀᴄʜᴇs Oғ Tʜᴇ Dᴀʏ 👇</b>", reply_markup=reply_markup)

    
@Client.on_message(filters.command('trendlist'))
async def trendlist(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))
    limit = 31
    if len(message.command) > 1:
        try:
            limit = int(message.command[1])
        except ValueError:
            await message.reply_text("Invalid number format.\nPlease provide a valid number after the /trendlist command.")
            return 
    try:
        top_messages = await silentdb.get_top_messages(limit)
    except Exception as e:
        await message.reply_text(f"Error retrieving messages: {str(e)}")
        return  
    if not top_messages:
        await message.reply_text("No top messages found.")
        return 
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        if msg.lower() not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg.lower())
            truncated_messages.append(msg[:32] + '...' if len(msg) > 35 else msg)
    if not truncated_messages:
        await message.reply_text("No valid top messages found.")
        return  
    formatted_list = "\n".join([f"{i+1}. <b>{msg}</b>" for i, msg in enumerate(truncated_messages)])
    additional_message = "⚡️ 𝑨𝒍𝒍 𝒕𝒉𝒆 𝒓𝒆𝒔𝒖𝒍𝒕𝒔 𝒂𝒃𝒐𝒗𝒆 𝒄𝒐𝒎𝒆 𝒇𝒓𝒐𝒎 𝒘𝒉𝒂𝒕 𝒖𝒔𝒆𝒓𝒔 𝒉𝒂𝒗𝒆 𝒔𝒆𝒂𝒓𝒄𝒉𝒆𝒅 𝒇𝒐𝒓. 𝑻𝒉𝒆𝒚'𝒓𝒆 𝒔𝒉𝒐𝒘𝒏 𝒕𝒐 𝒚𝒐𝒖 𝒆𝒙𝒂𝒄𝒕𝒍𝒚 𝒂𝒔 𝒕𝒉𝒆𝒚 𝒘𝒆𝒓𝒆 𝒔𝒆𝒂𝒓𝒄𝒉𝒆𝒅, 𝒘𝒊𝒕𝒉𝒐𝒖𝒕 𝒂𝒏𝒚 𝒄𝒉𝒂𝒏𝒈𝒆𝒔 𝒃𝒚 𝒕𝒉𝒆 𝒐𝒘𝒏𝒆𝒓."
    formatted_list += f"\n\n{additional_message}"
    reply_text = f"<b>Top {len(truncated_messages)} Tʀᴀɴᴅɪɴɢ ᴏғ ᴛʜᴇ ᴅᴀʏ 👇:</b>\n\n{formatted_list}"
    await message.reply_text(reply_text)

@Client.on_message(filters.private & filters.command("pm_search") & filters.user(ADMINS))
async def set_pm_search(client, message):
    bot_id = client.me.id
    try:
        option = message.text.split(" ", 1)[1].strip().lower()
        enable_status = option in ['on', 'true']
    except (IndexError, ValueError):
        await message.reply_text("<b>💔 Invalid option. Please send 'on' or 'off' after the command..</b>")
        return
    try:
        await db.update_pm_search_status(bot_id, enable_status)
        response_text = (
            "<b> ᴘᴍ ꜱᴇᴀʀᴄʜ ᴇɴᴀʙʟᴇᴅ ✅</b>" if enable_status 
            else "<b> ᴘᴍ ꜱᴇᴀʀᴄʜ ᴅɪꜱᴀʙʟᴇᴅ ❌</b>"
        )
        await message.reply_text(response_text)
    except Exception as e:
        await log_error(client, f"Error in set_pm_search: {e}")
        await message.reply_text(f"<b>❗ An error occurred: {e}</b>")

@Client.on_message(filters.private & filters.command("movie_update") & filters.user(ADMINS))
async def set_movie_update_notification(client, message):
    bot_id = client.me.id
    try:
        option = message.text.split(" ", 1)[1].strip().lower()
        enable_status = option in ['on', 'true']
    except (IndexError, ValueError):
        await message.reply_text("<b>💔 Invalid option. Please send 'on' or 'off' after the command.</b>")
        return
    try:
        await db.update_movie_update_status(bot_id, enable_status)
        response_text = (
            "<b>ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ᴇɴᴀʙʟᴇᴅ ✅</b>" if enable_status 
            else "<b>ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ᴅɪꜱᴀʙʟᴇᴅ ❌</b>"
        )
        await message.reply_text(response_text)
    except Exception as e:
        await log_error(client, f"Error in set_movie_update_notification: {e}")
        await message.reply_text(f"<b>❗ An error occurred: {e}</b>")

@Client.on_message(filters.private & filters.command("maintenance") & filters.user(ADMINS))
async def set_maintenance_mode(client, message):
    bot_id = client.me.id
    try:
        option = message.text.split(" ", 1)[1].strip().lower()
        enable_status = option in ['on', 'true']
    except (IndexError, ValueError):
        await message.reply_text("💔 Invalid Option. Please Send 'on' or 'off' Along With Command.. Example- /maintenance on")
        return
    try:
        await db.update_maintenance_status(bot_id, enable_status)
        response_text = (
            "<b>ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ ᴇɴᴀʙʟᴇᴅ ✅</b>" if enable_status 
            else "<b>ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ ᴅɪꜱᴀʙʟᴇᴅ ❌</b>"
        )
        await message.reply_text(response_text)
    except Exception as e:
        await log_error(client, f"Error in set_maintenance_mode: {e}")
        await message.reply_text(f"<b>❗ An error occurred: {e}</b>")
        

@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def stop_button(bot, message):
    msg = await bot.send_message(text="<b><i>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛɪɴɢ</i></b>", chat_id=message.chat.id)       
    await asyncio.sleep(3)
    await msg.edit("<b><i><u>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛᴇᴅ</u> ✅</i></b>")
    os.execl(sys.executable, sys.executable, *sys.argv)


@Client.on_message(filters.command("reset_group"))
async def reset_group_command(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    grp_id = message.chat.id
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    sts = await message.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    btn = [[
        InlineKeyboardButton('🚫 ᴄʟᴏsᴇ 🚫', callback_data='close_data')
    ]]
    reply_markup = InlineKeyboardMarkup(btn)
    await save_group_settings(grp_id, 'shortner', SHORTENER_WEBSITE)
    await save_group_settings(grp_id, 'api', SHORTENER_API)
    await save_group_settings(grp_id, 'shortner_two', SHORTENER_WEBSITE2)
    await save_group_settings(grp_id, 'api_two', SHORTENER_API2)
    await save_group_settings(grp_id, 'shortner_three', SHORTENER_WEBSITE3)
    await save_group_settings(grp_id, 'api_three', SHORTENER_API3)
    await save_group_settings(grp_id, 'verify_time', TWO_VERIFY_GAP)
    await save_group_settings(grp_id, 'third_verify_time', THREE_VERIFY_GAP)
    await save_group_settings(grp_id, 'template', IMDB_TEMPLATE)
    await save_group_settings(grp_id, 'tutorial', TUTORIAL)
    await save_group_settings(grp_id, 'tutorial_2', TUTORIAL_2)
    await save_group_settings(grp_id, 'tutorial_3', TUTORIAL_3)
    await save_group_settings(grp_id, 'caption', CUSTOM_FILE_CAPTION)
    await save_group_settings(grp_id, 'log', LOG_VR_CHANNEL)
    await save_group_settings(grp_id, 'is_verify', IS_VERIFY)
    await save_group_settings(grp_id, 'fsub_id', AUTH_CHANNEL)
    await message.reply_text('ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ...')

@Client.on_message(filters.command('set_fsub'))
async def set_fsub(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    try:
        channel_id = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text("<b>ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ\n\nꜱᴇɴᴅ ᴍᴇ ᴄʜᴀɴɴᴇʟ ɪᴅ ᴡɪᴛʜ ᴄᴏᴍᴍᴀɴᴅ, ʟɪᴋᴇ <code>/set_fsub -100******</code></b>")
    except ValueError:
        return await message.reply_text('<b>ᴍᴀᴋᴇ ꜱᴜʀᴇ ᴛʜᴇ ɪᴅ ɪꜱ ᴀɴ ɪɴᴛᴇɢᴇʀ.</b>')
    try:
        chat = await client.get_chat(channel_id)
    except Exception as e:
        return await message.reply_text(f"<b><code>{channel_id}</code> ɪꜱ ɪɴᴠᴀʟɪᴅ. ᴍᴀᴋᴇ ꜱᴜʀᴇ <a href=https://t.me/{temp.B_LINK} ʙᴏᴛ</a> ɪꜱ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ\n\n<code>{e}</code></b>")
    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply_text(f"🫥 <code>{channel_id}</code> ᴛʜɪꜱ ɪꜱ ɴᴏᴛ ᴄʜᴀɴɴᴇʟ, ꜱᴇɴᴅ ᴍᴇ ᴏɴʟʏ ᴄʜᴀɴɴᴇʟ ɪᴅ ɴᴏᴛ ɢʀᴏᴜᴘ ɪᴅ</b>")
    await save_group_settings(grp_id, 'fsub_id', [channel_id])
    mention = message.from_user.mention
    await client.send_message(LOG_API_CHANNEL, f"#Fsub_Channel_set\n\nᴜꜱᴇʀ - {mention} ꜱᴇᴛ ᴛʜᴇ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}:\n\nꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ - {chat.title}\nɪᴅ - `{channel_id}`")
    await message.reply_text(f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\nᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ - {chat.title}\nɪᴅ - <code>{channel_id}</code></b>")

@Client.on_message(filters.command('remove_fsub'))
async def remove_fsub(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")       
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    settings = await get_settings(grp_id)
    if (c in AUTH_CHANNEL for c in settings['fsub_id']):
        await message.reply_text("<b>ᴄᴜʀʀᴇɴᴛʟʏ ɴᴏ ᴀɴʏ ғᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ.... <code>[ᴅᴇғᴀᴜʟᴛ ᴀᴄᴛɪᴠᴀᴛᴇ]</code></b>")
    else:
        await save_group_settings(grp_id, 'fsub_id', AUTH_CHANNEL)
        mention = message.from_user.mention
        await client.send_message(LOG_API_CHANNEL, f"#Remove_Fsub_Channel\n\nᴜꜱᴇʀ - {mention} ʀᴇᴍᴏᴠᴇ ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ ꜰʀᴏᴍ {title}")
        await message.reply_text(f"<b>✅ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ꜰᴏʀᴄᴇ ꜱᴜʙ ᴄʜᴀɴɴᴇʟ.</b>")         


@Client.on_message(filters.command('details'))
async def all_settings(client, message):    
    try:
        bot_id = client.me.id
        maintenance_mode = await db.get_maintenance_status(bot_id)
        if maintenance_mode and message.from_user.id not in ADMINS:
            await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
            return
        chat_type = message.chat.type
        if chat_type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
        grp_id = message.chat.id
        title = message.chat.title
        
        if not await is_check_admin(client, grp_id, message.from_user.id):
            return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>') 
        
        settings = await get_settings(grp_id)
        nbbotz = f"""<b>⚙️ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ - {title}</b>

✅️ <b><u>1sᴛ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings["shortner"]}</code>
<b>ᴀᴘɪ</b> - <code>{settings["api"]}</code>

✅️ <b><u>2ɴᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings["shortner_two"]}</code>
<b>ᴀᴘɪ</b> - <code>{settings["api_two"]}</code>

✅️ <b><u>𝟹ʀᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ</u></b>
<b>ɴᴀᴍᴇ</b> - <code>{settings["shortner_three"]}</code>
<b>ᴀᴘɪ</b> - <code>{settings["api_three"]}</code>

⏰ <b>2ɴᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ</b> - <code>{settings["verify_time"]}</code>

⏰ <b>𝟹ʀᴅ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ᴛɪᴍᴇ</b> - <code>{settings['third_verify_time']}</code>

1️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 1</b> - {settings['tutorial']}

2️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 2</b> - {settings.get('tutorial_2', TUTORIAL_2)}

3️⃣ <b>ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ 3</b> - {settings.get('tutorial_3', TUTORIAL_3)}

📝 <b>ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ</b> - <code>{settings['log']}</code>

🚫 ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ ɪᴅ - `{settings['fsub_id']}`

🎯 <b>ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ</b> - <code>{settings['template']}</code>

📂 <b>ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏɴ</b> - <code>{settings['caption']}</code>

📌 <b><i>ɴᴏᴛᴇ :- ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇꜱᴇᴛ ʏᴏᴜʀ ꜱᴇᴛᴛɪɴɢꜱ ᴊᴜꜱᴛ ꜱᴇɴᴅ <code>/reset_group</code> ᴄᴏᴍᴍᴀɴᴅ.</i></b>
"""        
        btn = [[            
            InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_data")
        ]]
        reply_markup=InlineKeyboardMarkup(btn)
        dlt=await message.reply_text(nbbotz, reply_markup=reply_markup, disable_web_page_preview=True)
        await asyncio.sleep(300)
        await dlt.delete()
    except Exception as e:
        LOGGER.error(f"Error : {e}")
        await message.reply_text(f"Error: {e}")

@Client.on_message(filters.command('group_cmd'))
async def group_commands(client, message):
    bot_id = client.me.id
    maintenance_mode = await db.get_maintenance_status(bot_id)
    if maintenance_mode and message.from_user.id not in ADMINS:
        await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
        return
    user = message.from_user.mention
    user_id = message.from_user.id
    await message.reply_text(script.GROUP_CMD, disable_web_page_preview=True)

@Client.on_message(filters.command('admin_cmd') & filters.user(ADMINS))
async def admin_commands(client, message):
    user = message.from_user.mention
    user_id = message.from_user.id
    await message.reply_text(script.ADMIN_CMD, disable_web_page_preview=True)

@Client.on_message(filters.private & filters.command("movies"))
async def siletxbotz_list_movies(client, message):
    try:
        bot_id = client.me.id
        maintenance_mode = await db.get_maintenance_status(bot_id)
        if maintenance_mode and message.from_user.id not in ADMINS:
            await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
            return
        movies = await siletxbotz_get_movies()
        if not movies:
            return await message.reply("❌ No Recent Movies Found", parse_mode=ParseMode.HTML)       
        msg = "<b>Latest Uploads List ✅</b>\n\n"
        msg += "<b>🎬 Movies:</b>\n"
        msg += "\n".join(f"<b>{i+1}. {m}</b>" for i, m in enumerate(movies))
        await message.reply(msg[:4096], parse_mode=ParseMode.HTML)
    except Exception as e:
        LOGGER.error(f"Error in siletxbotz_list_movies: {e}")
        await message.reply("An Error Occurred ☹️", parse_mode=ParseMode.HTML)

@Client.on_message(filters.private & filters.command("series"))
async def siletxbotz_list_series(client, message):
    try:
        bot_id = client.me.id
        maintenance_mode = await db.get_maintenance_status(bot_id)
        if maintenance_mode and message.from_user.id not in ADMINS:
            await message.reply_text(f"ɪ ᴀᴍ ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ 🛠️. ɪ ᴡɪʟʟ ʙᴇ ʙᴀᴄᴋ ꜱᴏᴏɴ 🔜", disable_web_page_preview=True)
            return
        series_data = await siletxbotz_get_series()
        if not series_data:
            return await message.reply("❌ No Recent Series Found", parse_mode=ParseMode.HTML)       
        msg = "<b>Latest Uploades List ✅</b>\n\n"
        msg += "<b>📺 Series:</b>\n"
        for i, (title, seasons) in enumerate(series_data.items(), 1):
            season_list = ", ".join(f"{s}" for s in seasons)
            msg += f"<b>{i}. {title} - Season {season_list}</b>\n"
        await message.reply(msg[:4096], parse_mode=ParseMode.HTML)
    except Exception as e:
        LOGGER.error(f"Error in siletxbotz_list_series: {e}")
        await message.reply("An Error Occurred ☹️", parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.command("resetall") & filters.user(ADMINS))
async def reset_all_settings(client, message):
    try:
        reset_count = await db.silentx_reset_settings()
        await message.reply(
            f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ ꜰᴏʀ {reset_count} ɢʀᴏᴜᴘꜱ. ᴅᴇꜰᴀᴜʟᴛ ᴠᴀʟᴜᴇꜱ ᴡɪʟʟ ʙᴇ ᴜꜱᴇᴅ ✅</b>",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error Processing Reset All Settings Command: {str(e)}")
        await message.reply("<b>ᴇʀʀᴏʀ 🚫.oᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴅᴇʟᴇᴛɪɴɢ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ! ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>", quote=True)


group_links_cache = {}

@Client.on_message(filters.private & filters.command("group_link") & filters.user(ADMINS))
async def group_link_command(client, message):
    wait_msg = await message.reply("<b>🔍 Fetching group links... Please wait...</b>")
    try:
        chats = await db.get_all_chats()
        groups_list = []
        async for chat in chats:
            chat_id = int(chat['id'])
            chat_title = chat.get('title', 'Unknown')
            try:
                chat_info = await client.get_chat(chat_id)
                member = await client.get_chat_member(chat_id, client.me.id)
                if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                    if chat_info.invite_link:
                        invite_link = chat_info.invite_link
                    else:
                        try:
                            invite_link = await client.export_chat_invite_link(chat_id)
                        except:
                            invite_link = "N/A (No permission)"
                else:
                    invite_link = "N/A (Not admin)"
                groups_list.append({
                    "id": chat_id,
                    "title": chat_info.title or chat_title,
                    "link": invite_link
                })
            except Exception as e:
                groups_list.append({
                    "id": chat_id,
                    "title": chat_title,
                    "link": f"N/A (Error)"
                })
        
        if not groups_list:
            await wait_msg.edit("<b>❌ No groups found!</b>")
            return
        
        user_id = message.from_user.id
        group_links_cache[user_id] = groups_list
        await send_group_links_page(client, wait_msg, user_id, 0)
    except Exception as e:
        LOGGER.error(f"Error in group_link command: {e}")
        await wait_msg.edit(f"<b>❌ Error fetching groups: {e}</b>")

async def send_group_links_page(client, message, user_id, page):
    groups_list = group_links_cache.get(user_id, [])
    if not groups_list:
        await message.edit("<b>❌ Session expired. Use /group_link again.</b>")
        return
    
    per_page = 10
    total_groups = len(groups_list)
    total_pages = (total_groups + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_groups)
    
    text = f"<b>📋 Group Links (Page {page + 1}/{total_pages})</b>\n"
    text += f"<b>Total Groups: {total_groups}</b>\n\n"
    
    for i, group in enumerate(groups_list[start_idx:end_idx], start=start_idx + 1):
        title = group['title'][:25] + "..." if len(group['title']) > 25 else group['title']
        if group['link'].startswith("http"):
            text += f"<b>{i}. <a href='{group['link']}'>{title}</a></b>\n"
        else:
            text += f"<b>{i}. {title}</b> - {group['link']}\n"
    
    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"grplink#{user_id}#{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"grplink#{user_id}#{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("❌ Close", callback_data=f"grplink#{user_id}#close")])
    
    await message.edit(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

@Client.on_callback_query(filters.regex(r'^grplink#'))
async def group_link_callback(client, query):
    data = query.data.split("#")
    user_id = int(data[1])
    
    if query.from_user.id != user_id and query.from_user.id not in ADMINS:
        return await query.answer("❌ This is not for you!", show_alert=True)
    
    action = data[2]
    if action == "close":
        group_links_cache.pop(user_id, None)
        await query.message.delete()
        return
    
    page = int(action)
    await send_group_links_page(client, query.message, user_id, page)       


# Force Add Feature Commands
@Client.on_message(filters.command("on_forceadd") & filters.group)
async def enable_forceadd_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    chat_id = message.chat.id
    await db.enable_forceadd(chat_id)
    required = await db.get_forceadd_count(chat_id)
    await message.reply_text(
        f"✅ <b>ꜰᴏʀᴄᴇ ᴀᴅᴅ ꜰᴇᴀᴛᴜʀᴇ ᴇɴᴀʙʟᴇᴅ!</b>\n\n"
        f"👥 ʀᴇǫᴜɪʀᴇᴅ ᴍᴇᴍʙᴇʀꜱ ᴛᴏ ᴀᴅᴅ: <b>{required}</b>\n\n"
        f"ᴜꜱᴇ <code>/user_count [number]</code> ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ʀᴇǫᴜɪʀᴇᴅ ᴄᴏᴜɴᴛ."
    )


@Client.on_message(filters.command("off_forceadd") & filters.group)
async def disable_forceadd_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    chat_id = message.chat.id
    await db.disable_forceadd(chat_id)
    await message.reply_text("❌ <b>ꜰᴏʀᴄᴇ ᴀᴅᴅ ꜰᴇᴀᴛᴜʀᴇ ᴅɪꜱᴀʙʟᴇᴅ!</b>")


@Client.on_message(filters.command("user_count") & filters.group)
async def set_user_count_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    if len(message.command) < 2:
        current = await db.get_forceadd_count(message.chat.id)
        return await message.reply_text(
            f"📊 <b>ᴄᴜʀʀᴇɴᴛ ʀᴇǫᴜɪʀᴇᴅ ᴀᴅᴅ ᴄᴏᴜɴᴛ: {current}</b>\n\n"
            f"ᴜꜱᴀɢᴇ: <code>/user_count [number]</code>\n"
            f"ᴇxᴀᴍᴘʟᴇ: <code>/user_count 5</code>"
        )
    
    try:
        count = int(message.command[1])
        if count < 1 or count > 50:
            return await message.reply_text("❌ ᴄᴏᴜɴᴛ ᴍᴜꜱᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 50!")
        
        await db.set_forceadd_count(message.chat.id, count)
        await message.reply_text(
            f"✅ <b>ʀᴇǫᴜɪʀᴇᴅ ᴀᴅᴅ ᴄᴏᴜɴᴛ ꜱᴇᴛ ᴛᴏ: {count}</b>\n\n"
            f"ᴜꜱᴇʀꜱ ᴍᴜꜱᴛ ᴀᴅᴅ {count} ᴍᴇᴍʙᴇʀꜱ ᴛᴏ ꜱᴇᴀʀᴄʜ."
        )
    except ValueError:
        await message.reply_text("❌ ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!")


@Client.on_message(filters.command("repeat_forceadd") & filters.private)
async def reset_forceadd_global_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    count = await db.reset_global_forceadd_counts()
    await message.reply_text(
        f"✅ <b>ꜰᴏʀᴄᴇ ᴀᴅᴅ ᴄᴏᴜɴᴛꜱ ʀᴇꜱᴇᴛ ɢʟᴏʙᴀʟʟʏ!</b>\n\n"
        f"🔄 ʀᴇꜱᴇᴛ ᴄᴏᴜɴᴛꜱ ɪɴ {count} ɢʀᴏᴜᴘꜱ.\n"
        f"ᴀʟʟ ᴜꜱᴇʀꜱ ᴡɪʟʟ ɴᴇᴇᴅ ᴛᴏ ᴀᴅᴅ ᴍᴇᴍʙᴇʀꜱ ᴀɢᴀɪɴ."
    )


@Client.on_message(filters.command("repeat_forceadd") & filters.group)
async def reset_forceadd_group_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    await db.reset_all_user_add_counts(message.chat.id)
    await message.reply_text(
        f"✅ <b>ꜰᴏʀᴄᴇ ᴀᴅᴅ ᴄᴏᴜɴᴛꜱ ʀᴇꜱᴇᴛ ꜰᴏʀ ᴛʜɪꜱ ɢʀᴏᴜᴘ!</b>\n\n"
        f"🔄 ᴀʟʟ ᴜꜱᴇʀꜱ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ ᴡɪʟʟ ɴᴇᴇᴅ ᴛᴏ ᴀᴅᴅ ᴍᴇᴍʙᴇʀꜱ ᴀɢᴀɪɴ."
    )


@Client.on_message(filters.command("forceadd_status") & filters.group)
async def forceadd_status_cmd(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ ᴏɴʟʏ ʙᴏᴛ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ!")
    
    chat_id = message.chat.id
    enabled = await db.is_forceadd_enabled(chat_id)
    required = await db.get_forceadd_count(chat_id)
    
    status = "✅ ᴇɴᴀʙʟᴇᴅ" if enabled else "❌ ᴅɪꜱᴀʙʟᴇᴅ"
    await message.reply_text(
        f"📊 <b>ꜰᴏʀᴄᴇ ᴀᴅᴅ ꜱᴛᴀᴛᴜꜱ</b>\n\n"
        f"ꜱᴛᴀᴛᴜꜱ: {status}\n"
        f"ʀᴇǫᴜɪʀᴇᴅ ᴍᴇᴍʙᴇʀꜱ: <b>{required}</b>"
    )


# Track new members added by users (direct add)
@Client.on_message(filters.group & filters.new_chat_members)
async def track_new_members(client, message):
    import logging
    logger = logging.getLogger(__name__)
    
    chat_id = message.chat.id
    logger.info(f"[DirectAdd] New members event in chat {chat_id}")
    
    if not await db.is_forceadd_enabled(chat_id):
        logger.info(f"[DirectAdd] ForceAdd not enabled in {chat_id}")
        return
    
    adder = message.from_user
    logger.info(f"[DirectAdd] Adder: {adder}")
    
    if not adder:
        logger.info(f"[DirectAdd] No adder found, skipping")
        return
    
    logger.info(f"[DirectAdd] new_chat_members: {message.new_chat_members}")
    new_members = [m for m in message.new_chat_members if not m.is_bot and m.id != adder.id]
    added_count = len(new_members)
    logger.info(f"[DirectAdd] Adder {adder.id} added {added_count} members: {[m.id for m in new_members]}")
    
    if added_count > 0:
        await db.increment_user_add_count(chat_id, adder.id, added_count)
        current = await db.get_user_add_count(chat_id, adder.id)
        required = await db.get_forceadd_count(chat_id)
        logger.info(f"[DirectAdd] Updated count for {adder.id}: {current}/{required}")
        
        if current >= required:
            await message.reply_text(
                f"🎉 <b>ᴛʜᴀɴᴋꜱ {adder.mention}!</b>\n\n"
                f"ʏᴏᴜ ʜᴀᴠᴇ ᴀᴅᴅᴇᴅ {current}/{required} ᴍᴇᴍʙᴇʀꜱ.\n"
                f"✅ ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ꜱᴇᴀʀᴄʜ ꜰᴏʀ ᴍᴏᴠɪᴇꜱ!"
            )
        else:
            remaining = required - current
            await message.reply_text(
                f"👍 <b>ɢᴏᴏᴅ ᴊᴏʙ {adder.mention}!</b>\n\n"
                f"ʏᴏᴜ ʜᴀᴠᴇ ᴀᴅᴅᴇᴅ {current}/{required} ᴍᴇᴍʙᴇʀꜱ.\n"
                f"📌 ᴀᴅᴅ {remaining} ᴍᴏʀᴇ ᴛᴏ ꜱᴇᴀʀᴄʜ ꜰᴏʀ ᴍᴏᴠɪᴇꜱ."
            )
    else:
        logger.info(f"[DirectAdd] No valid members to count (self-join or bots)")


# Track members who join via invite links OR added directly by another user
@Client.on_chat_member_updated(filters.group)
async def track_invite_link_joins(client, chat_member_updated):
    import logging
    logger = logging.getLogger(__name__)
    
    chat_id = chat_member_updated.chat.id
    
    if not await db.is_forceadd_enabled(chat_id):
        return
    
    new_member = chat_member_updated.new_chat_member
    old_member = chat_member_updated.old_chat_member
    
    logger.info(f"[ForceAdd] Chat member update in {chat_id}")
    
    if not new_member:
        return
    
    old_status = old_member.status.value if old_member and hasattr(old_member.status, 'value') else (old_member.status if old_member else "none")
    new_status = new_member.status.value if hasattr(new_member.status, 'value') else new_member.status
    
    logger.info(f"[ForceAdd] Old: {old_status}, New: {new_status}")
    
    is_new_join = (not old_member or old_status in ["left", "banned", "restricted", "kicked"]) and new_status == "member"
    
    if not is_new_join:
        return
    
    if new_member.user.is_bot:
        return
    
    joined_user = new_member.user
    invite_link = chat_member_updated.invite_link
    adder = chat_member_updated.from_user
    
    logger.info(f"[ForceAdd] Joined: {joined_user.id}, Adder: {adder}, Invite: {invite_link}")
    
    if invite_link:
        link_str = invite_link.invite_link
        logger.info(f"[ForceAdd] Invite link used: {link_str}")
        inviter_id = await db.get_user_by_invite_link(chat_id, link_str)
        logger.info(f"[ForceAdd] Found inviter from DB: {inviter_id}")
        
        if inviter_id:
            await db.increment_user_add_count(chat_id, inviter_id, 1)
            current = await db.get_user_add_count(chat_id, inviter_id)
            required = await db.get_forceadd_count(chat_id)
            
            try:
                inviter = await client.get_users(inviter_id)
                if current >= required:
                    await client.send_message(
                        chat_id,
                        f"🎉 <b>ᴛʜᴀɴᴋꜱ {inviter.mention}!</b>\n\n"
                        f"ꜱᴏᴍᴇᴏɴᴇ ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ! ({current}/{required})\n"
                        f"✅ ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ꜱᴇᴀʀᴄʜ ꜰᴏʀ ᴍᴏᴠɪᴇꜱ!"
                    )
                else:
                    remaining = required - current
                    await client.send_message(
                        chat_id,
                        f"👍 <b>ɢᴏᴏᴅ ᴊᴏʙ {inviter.mention}!</b>\n\n"
                        f"ꜱᴏᴍᴇᴏɴᴇ ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ! ({current}/{required})\n"
                        f"📌 {remaining} ᴍᴏʀᴇ ᴛᴏ ᴜɴʟᴏᴄᴋ ꜱᴇᴀʀᴄʜ."
                    )
            except Exception as e:
                logger.error(f"[ForceAdd] Error notifying inviter: {e}")
    
    elif adder and adder.id != joined_user.id:
        logger.info(f"[ForceAdd] Direct add detected! Adder: {adder.id}, Added: {joined_user.id}")
        await db.increment_user_add_count(chat_id, adder.id, 1)
        current = await db.get_user_add_count(chat_id, adder.id)
        required = await db.get_forceadd_count(chat_id)
        logger.info(f"[ForceAdd] Updated count for {adder.id}: {current}/{required}")
        
        try:
            if current >= required:
                await client.send_message(
                    chat_id,
                    f"🎉 <b>ᴛʜᴀɴᴋꜱ {adder.mention}!</b>\n\n"
                    f"ʏᴏᴜ ᴀᴅᴅᴇᴅ ᴀ ᴍᴇᴍʙᴇʀ! ({current}/{required})\n"
                    f"✅ ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ꜱᴇᴀʀᴄʜ ꜰᴏʀ ᴍᴏᴠɪᴇꜱ!"
                )
            else:
                remaining = required - current
                await client.send_message(
                    chat_id,
                    f"👍 <b>ɢᴏᴏᴅ ᴊᴏʙ {adder.mention}!</b>\n\n"
                    f"ʏᴏᴜ ᴀᴅᴅᴇᴅ ᴀ ᴍᴇᴍʙᴇʀ! ({current}/{required})\n"
                    f"📌 {remaining} ᴍᴏʀᴇ ᴛᴏ ᴜɴʟᴏᴄᴋ ꜱᴇᴀʀᴄʜ."
                )
        except Exception as e:
            logger.error(f"[ForceAdd] Error notifying adder: {e}")
