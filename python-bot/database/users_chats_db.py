import motor.motor_asyncio
from info import *  
from datetime import timedelta
import time, datetime, pytz
import os as _os
from pymongo.errors import DuplicateKeyError
from pymongo import MongoClient
from logging_helper import LOGGER

# Free tier 512 MB. Cleanup junk collections (verify_id, miniapp_tokens) above threshold.
USERSDB_CLEANUP_THRESHOLD_MB = int(_os.environ.get('USERSDB_CLEANUP_THRESHOLD_MB', '460'))
USERSDB_CLEANUP_BATCH = int(_os.environ.get('USERSDB_CLEANUP_BATCH', '2000'))


def _is_quota_error(e):
    s = str(e).lower()
    return ('space quota' in s) or ('over your space' in s) or ('quota' in s and '512' in s)


class Database:    
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.grp = self.db.groups
        self.users = self.db.uersz
        self.botcol = self.db.bot_settings
        self.misc = self.db.misc
        self.verify_id = self.db.verify_id 
        self.codes = self.db.codes
        self.connection = self.db.connections
        self.forceadd = self.db.forceadd
        self.miniapp_tokens = self.db.miniapp_tokens

    async def _db_size_mb(self):
        try:
            stats = await self.db.command("dbstats")
            used = int(stats.get('storageSize', 0)) + int(stats.get('indexSize', 0))
            if used == 0:
                used = int(stats.get('dataSize', 0))
            return used / 1024 / 1024
        except Exception:
            return 0

    async def auto_cleanup(self):
        """If users-DB above threshold, delete oldest junk: expired tokens, old verify_ids, expired premiums."""
        try:
            size_mb = await self._db_size_mb()
            if size_mb < USERSDB_CLEANUP_THRESHOLD_MB:
                return 0
            LOGGER.warning(f"[USERSDB-CLEANUP] size {size_mb:.1f} MB >= {USERSDB_CLEANUP_THRESHOLD_MB} MB. Cleaning junk collections...")
            total = 0
            now = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
            # 1) expired miniapp tokens
            try:
                r = await self.miniapp_tokens.delete_many({'expires_at': {'$lt': now}})
                total += r.deleted_count
                LOGGER.warning(f"[USERSDB-CLEANUP] expired miniapp_tokens: {r.deleted_count}")
            except Exception as e:
                LOGGER.error(f"[USERSDB-CLEANUP] miniapp_tokens: {e}")
            # 2) old verify_id docs (batch oldest)
            for _ in range(10):
                size_mb = await self._db_size_mb()
                if size_mb < USERSDB_CLEANUP_THRESHOLD_MB:
                    break
                try:
                    cursor = self.verify_id.find({}, {'_id': 1}).sort('$natural', 1).limit(USERSDB_CLEANUP_BATCH)
                    ids = [d['_id'] async for d in cursor]
                    if not ids:
                        break
                    r = await self.verify_id.delete_many({'_id': {'$in': ids}})
                    total += r.deleted_count
                    LOGGER.warning(f"[USERSDB-CLEANUP] verify_id: {r.deleted_count}")
                except Exception as e:
                    LOGGER.error(f"[USERSDB-CLEANUP] verify_id loop: {e}")
                    break
            # 3) old VERIFIED miniapp tokens (already used) — never delete unexpired pending tokens
            for _ in range(10):
                size_mb = await self._db_size_mb()
                if size_mb < USERSDB_CLEANUP_THRESHOLD_MB:
                    break
                try:
                    # Only delete tokens that are either verified (already consumed)
                    # or created more than 1 hour ago (well past 15-min expiry).
                    cutoff = now - timedelta(hours=1)
                    cursor = self.miniapp_tokens.find(
                        {"$or": [{"verified": True}, {"created_at": {"$lt": cutoff}}]},
                        {'_id': 1}
                    ).sort('$natural', 1).limit(USERSDB_CLEANUP_BATCH)
                    ids = [d['_id'] async for d in cursor]
                    if not ids:
                        break
                    r = await self.miniapp_tokens.delete_many({'_id': {'$in': ids}})
                    total += r.deleted_count
                    LOGGER.warning(f"[USERSDB-CLEANUP] miniapp_tokens(old/verified): {r.deleted_count}")
                except Exception as e:
                    LOGGER.error(f"[USERSDB-CLEANUP] miniapp_tokens loop: {e}")
                    break
            # 4) expired premium users (expiry_time in past) — only clear field, keep user
            try:
                await self.users.update_many(
                    {"expiry_time": {"$lt": datetime.datetime.now()}},
                    {"$set": {"expiry_time": None}}
                )
            except Exception:
                pass
            # 5) compact junk collections
            for c in ('verify_id', 'miniapp_tokens'):
                try:
                    await self.db.command({'compact': c})
                except Exception:
                    pass
            LOGGER.warning(f"[USERSDB-CLEANUP] total deleted = {total}")
            return total
        except Exception as e:
            LOGGER.error(f"[USERSDB-CLEANUP] failed: {e}")
            return 0

    # ====== Mini App tokens kept IN-MEMORY (not in DB) ======
    # Reason: Atlas free tier (512 MB) frequently quota-locks the users-DB,
    # which made `update_one` silently fail and produced "Link expired or invalid"
    # the moment the user tapped "Watch ads & get file". Tokens only need to live
    # for ~15 min, so a process-local dict is more than enough and is unaffected
    # by DB size pressure.
    _miniapp_mem = {}

    @classmethod
    def _miniapp_purge(cls):
        now = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
        dead = [k for k, v in cls._miniapp_mem.items() if v.get('expires_at') and v['expires_at'] < now]
        for k in dead:
            cls._miniapp_mem.pop(k, None)

    async def create_miniapp_token(self, token, user_id, grp_id, file_id, kind, expiry_seconds=900):
        """Store a Mini App token in memory. kind = 'sendall' or 'notcopy'."""
        now = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
        expires = now + timedelta(seconds=expiry_seconds)
        Database._miniapp_purge()
        Database._miniapp_mem[token] = {
            "_id": token,
            "user_id": int(user_id),
            "grp_id": int(grp_id) if grp_id else 0,
            "file_id": file_id,
            "kind": kind,
            "verified": False,
            "ads_watched": 0,
            "created_at": now,
            "expires_at": expires,
        }
        # Best-effort: also clear any old DB copy so collection drains over time
        try:
            await self.miniapp_tokens.delete_one({"_id": token})
        except Exception:
            pass

    async def get_miniapp_token(self, token):
        Database._miniapp_purge()
        return Database._miniapp_mem.get(token)

    async def mark_miniapp_verified(self, token, ads_watched):
        info = Database._miniapp_mem.get(token)
        if info:
            info["verified"] = True
            info["ads_watched"] = int(ads_watched)
            info["verified_at"] = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

    async def find_join_req(self, id, chnl):
        chnl = str(chnl)
        return bool(await self.db.request[chnl].find_one({'id': id})) 
     
    async def add_join_req(self, id, chnl):
        chnl = str(chnl)
        await self.db.request[chnl].insert_one({'id': id})

    async def del_join_req(self):
        if AUTH_REQ_CHANNEL:
            for c in AUTH_REQ_CHANNEL:
                c = str(c)
            result = await self.db.request[c].delete_many({})
            print(result)

    def new_user(self, id, name):
        return dict(
            id = id,
            name = name,
            ban_status=dict(
                is_banned=False,
                ban_reason="",
            ),
        )

    def new_group(self, id, title):
        return dict(
            id = id,
            title = title,
            chat_status=dict(
                is_disabled=False,
                reason="",
            ),
        )
    
    async def add_user(self, id, name):
        user = self.new_user(id, name)
        try:
            await self.col.insert_one(user)
        except Exception as e:
            LOGGER.error(f"[USERSDB] add_user failed for {id}: {e}")
            if _is_quota_error(e):
                try:
                    await self.auto_cleanup()
                    await self.col.insert_one(user)
                    return
                except Exception as e2:
                    LOGGER.error(f"[USERSDB] add_user retry failed: {e2}")
            # swallow — never crash search/start because of users-DB write
            return
    
    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)
    
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count
    
    async def remove_ban(self, id):
        ban_status = dict(
            is_banned=False,
            ban_reason=''
        )
        await self.col.update_one({'id': id}, {'$set': {'ban_status': ban_status}})
    
    async def ban_user(self, user_id, ban_reason="No Reason"):
        ban_status = dict(
            is_banned=True,
            ban_reason=ban_reason
        )
        await self.col.update_one({'id': user_id}, {'$set': {'ban_status': ban_status}})

    async def get_ban_status(self, id):
        default = dict(
            is_banned=False,
            ban_reason=''
        )
        user = await self.col.find_one({'id':int(id)})
        if not user:
            return default
        return user.get('ban_status', default)

    async def get_all_users(self):
        return self.col.find({})
    
    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})
        
    async def delete_chat(self, id):
        await self.grp.delete_many({'id': int(id)})    

    async def get_banned(self):
        users = self.col.find({'ban_status.is_banned': True})
        chats = self.grp.find({'chat_status.is_disabled': True})
        b_chats = [chat['id'] async for chat in chats]
        b_users = [user['id'] async for user in users]
        return b_users, b_chats
    
    async def add_chat(self, chat, title):
        chat = self.new_group(chat, title)
        await self.grp.insert_one(chat)
    
    async def get_chat(self, chat):
        chat = await self.grp.find_one({'id':int(chat)})
        return False if not chat else chat.get('chat_status')
    
    async def re_enable_chat(self, id):
        chat_status=dict(
            is_disabled=False,
            reason="",
            )
        await self.grp.update_one({'id': int(id)}, {'$set': {'chat_status': chat_status}})
        
    async def update_settings(self, id, settings):
        await self.grp.update_one({'id': int(id)}, {'$set': {'settings': settings}})
            
    async def get_settings(self, id):
        default = {
            'button': LINK_MODE,
            'botpm': P_TTI_SHOW_OFF,
            'file_secure': PROTECT_CONTENT,
            'imdb': IMDB,
            'spell_check': SPELL_CHECK_REPLY,
            'welcome': MELCOW_NEW_USERS,
            'auto_delete': AUTO_DELETE,
            'auto_ffilter': AUTO_FFILTER,
            'max_btn': MAX_BTN,
            'template': IMDB_TEMPLATE,
            'log': LOG_VR_CHANNEL,
            'tutorial': TUTORIAL,
            'tutorial_2': TUTORIAL_2,
            'tutorial_3': TUTORIAL_3,
            'shortner': SHORTENER_WEBSITE,
            'api': SHORTENER_API,
            'shortner_two': SHORTENER_WEBSITE2,
            'api_two': SHORTENER_API2,
            'shortner_three': SHORTENER_WEBSITE3,
            'api_three': SHORTENER_API3,
            'is_verify': IS_VERIFY,
            'verify_time': TWO_VERIFY_GAP,
            'third_verify_time': THREE_VERIFY_GAP,
            'caption': CUSTOM_FILE_CAPTION,
            'fsub_id': AUTH_CHANNEL
        }
        chat = await self.grp.find_one({'id':int(id)})
        if chat and 'settings' in chat:
            return chat['settings']
        else:
            return default.copy()

    async def silentx_reset_settings(self):
        try:
            result = await self.grp.update_many(
                {'settings': {'$exists': True}},
                {'$unset': {'settings': ''}}
            )
            modified_count = result.modified_count
            return modified_count
        except Exception as e:
            print(f"Error deleting settings for all groups: {str(e)}")
            raise
            
    async def disable_chat(self, chat, reason="No Reason"):
        chat_status=dict(
            is_disabled=True,
            reason=reason,
            )
        await self.grp.update_one({'id': int(chat)}, {'$set': {'chat_status': chat_status}})

    async def total_chat_count(self):
        count = await self.grp.count_documents({})
        return count
    
    async def get_all_chats(self):
        return self.grp.find({})

    async def get_db_size(self):
        return (await self.db.command("dbstats"))['dataSize']

    async def get_user(self, user_id):
        user_data = await self.users.find_one({"id": user_id})
        return user_data
    async def update_user(self, user_data):
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def get_notcopy_user(self, user_id):
        user_id = int(user_id)
        user = await self.misc.find_one({"user_id": user_id})
        ist_timezone = pytz.timezone('Asia/Kolkata')
        if not user:
            res = {
                "user_id": user_id,
                "last_verified": datetime.datetime(2020, 5, 17, 0, 0, 0, tzinfo=ist_timezone),
                "second_time_verified": datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_timezone),
            }
            user = await self.misc.insert_one(res)
        return user

    async def update_notcopy_user(self, user_id, value:dict):
        user_id = int(user_id)
        myquery = {"user_id": user_id}
        newvalues = {"$set": value}
        return await self.misc.update_one(myquery, newvalues)

    async def is_user_verified(self, user_id):
        user = await self.get_notcopy_user(user_id)
        try:
            pastDate = user["last_verified"]
        except Exception:
            user = await self.get_notcopy_user(user_id)
            pastDate = user["last_verified"]
        ist_timezone = pytz.timezone('Asia/Kolkata')
        pastDate = pastDate.astimezone(ist_timezone)
        current_time = datetime.datetime.now(tz=ist_timezone)
        seconds_since_midnight = (current_time - datetime.datetime(current_time.year, current_time.month, current_time.day, 0, 0, 0, tzinfo=ist_timezone)).total_seconds()
        time_diff = current_time - pastDate
        total_seconds = time_diff.total_seconds()
        return total_seconds <= seconds_since_midnight

    async def user_verified(self, user_id):
        user = await self.get_notcopy_user(user_id)
        try:
            pastDate = user["second_time_verified"]
        except Exception:
            user = await self.get_notcopy_user(user_id)
            pastDate = user["second_time_verified"]
        ist_timezone = pytz.timezone('Asia/Kolkata')
        pastDate = pastDate.astimezone(ist_timezone)
        current_time = datetime.datetime.now(tz=ist_timezone)
        seconds_since_midnight = (current_time - datetime.datetime(current_time.year, current_time.month, current_time.day, 0, 0, 0, tzinfo=ist_timezone)).total_seconds()
        time_diff = current_time - pastDate
        total_seconds = time_diff.total_seconds()
        return total_seconds <= seconds_since_midnight

    async def use_second_shortener(self, user_id, time):
        user = await self.get_notcopy_user(user_id)
        if not user.get("second_time_verified"):
            ist_timezone = pytz.timezone('Asia/Kolkata')
            await self.update_notcopy_user(user_id, {"second_time_verified":datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_timezone)})
            user = await self.get_notcopy_user(user_id)
        if await self.is_user_verified(user_id):
            try:
                pastDate = user["last_verified"]
            except Exception:
                user = await self.get_notcopy_user(user_id)
                pastDate = user["last_verified"]
            ist_timezone = pytz.timezone('Asia/Kolkata')
            pastDate = pastDate.astimezone(ist_timezone)
            current_time = datetime.datetime.now(tz=ist_timezone)
            time_difference = current_time - pastDate
            if time_difference > datetime.timedelta(seconds=time):
                pastDate = user["last_verified"].astimezone(ist_timezone)
                second_time = user["second_time_verified"].astimezone(ist_timezone)
                return second_time < pastDate
        return False

    async def use_third_shortener(self, user_id, time):
        user = await self.get_notcopy_user(user_id)
        if not user.get("third_time_verified"):
            ist_timezone = pytz.timezone('Asia/Kolkata')
            await self.update_notcopy_user(user_id, {"third_time_verified":datetime.datetime(2018, 5, 17, 0, 0, 0, tzinfo=ist_timezone)})
            user = await self.get_notcopy_user(user_id)
        if await self.user_verified(user_id):
            try:
                pastDate = user["second_time_verified"]
            except Exception:
                user = await self.get_notcopy_user(user_id)
                pastDate = user["second_time_verified"]
            ist_timezone = pytz.timezone('Asia/Kolkata')
            pastDate = pastDate.astimezone(ist_timezone)
            current_time = datetime.datetime.now(tz=ist_timezone)
            time_difference = current_time - pastDate
            if time_difference > datetime.timedelta(seconds=time):
                pastDate = user["second_time_verified"].astimezone(ist_timezone)
                second_time = user["third_time_verified"].astimezone(ist_timezone)
                return second_time < pastDate
        return False
   
    async def create_verify_id(self, user_id: int, hash):
        res = {"user_id": user_id, "hash":hash, "verified":False}
        try:
            return await self.verify_id.insert_one(res)
        except Exception as e:
            LOGGER.error(f"[USERSDB] create_verify_id failed: {e}")
            if _is_quota_error(e):
                try:
                    await self.auto_cleanup()
                    return await self.verify_id.insert_one(res)
                except Exception as e2:
                    LOGGER.error(f"[USERSDB] create_verify_id retry failed: {e2}")
            return None

    async def get_verify_id_info(self, user_id: int, hash):
        try:
            return await self.verify_id.find_one({"user_id": user_id, "hash": hash})
        except Exception as e:
            LOGGER.error(f"[USERSDB] get_verify_id_info failed: {e}")
            return None

    async def update_verify_id_info(self, user_id, hash, value: dict):
        myquery = {"user_id": user_id, "hash": hash}
        newvalues = { "$set": value }
        try:
            return await self.verify_id.update_one(myquery, newvalues)
        except Exception as e:
            LOGGER.error(f"[USERSDB] update_verify_id_info failed: {e}")
            if _is_quota_error(e):
                try:
                    await self.auto_cleanup()
                    return await self.verify_id.update_one(myquery, newvalues)
                except Exception as e2:
                    LOGGER.error(f"[USERSDB] update_verify_id_info retry failed: {e2}")
            return None
        
    async def has_premium_access(self, user_id):
        user_data = await self.get_user(user_id)
        if user_data:
            expiry_time = user_data.get("expiry_time")
            if expiry_time is None:
                return False
            elif isinstance(expiry_time, datetime.datetime) and datetime.datetime.now() <= expiry_time:
                return True
            else:
                await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
        return False
        
    async def update_user(self, user_data):
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def update_one(self, filter_query, update_data):
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception as e:
            print(f"Error updating document: {e}")
            return False
            
    # Premium expired reminder ( This Code Modified By @BOT_OWNER26)
    async def get_expired(self, current_time):
        expired_users = []
        cursor = self.users.find({"expiry_time": {"$lt": current_time}})
        async for user in cursor:
            expired_users.append(user)
        return expired_users

    # Premium expired reminder ( This Code Modified By @BOT_OWNER26)
    async def get_expiring_soon(self, label, delta):
        reminder_key = f"reminder_{label}_sent"
        now = datetime.datetime.utcnow()
        target_time = now + delta
        window = timedelta(seconds=30)

        start_range = target_time - window
        end_range = target_time + window

        reminder_users = []
        cursor = self.users.find({
            "expiry_time": {"$gte": start_range, "$lte": end_range},
            reminder_key: {"$ne": True}
        })

        async for user in cursor:
            reminder_users.append(user)
            await self.users.update_one(
                {"id": user["id"]}, {"$set": {reminder_key: True}}
            )

        return reminder_users

    async def remove_premium_access(self, user_id):
        return await self.update_one(
            {"id": user_id}, {"$set": {"expiry_time": None}}
        )

    async def check_trial_status(self, user_id):
        user_data = await self.get_user(user_id)
        if user_data:
            return user_data.get("has_free_trial", False)
        return False

    async def give_free_trial(self, user_id):
        user_id = user_id
        seconds = 5*60         
        expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        user_data = {"id": user_id, "expiry_time": expiry_time, "has_free_trial": True}
        await self.users.update_one({"id": user_id}, {"$set": user_data}, upsert=True)

    async def all_premium_users(self):
        count = await self.users.count_documents({
        "expiry_time": {"$gt": datetime.datetime.now()}
        })
        return count
    
    async def get_bot_setting(self, bot_id, setting_key, default_value):
        bot = await self.botcol.find_one({'id': int(bot_id)}, {setting_key: 1, '_id': 0})
        return bot[setting_key] if bot and setting_key in bot else default_value
        
    async def update_bot_setting(self, bot_id, setting_key, value):
        await self.botcol.update_one(
            {'id': int(bot_id)}, 
            {'$set': {setting_key: value}}, 
            upsert=True
        )

    async def connect_group(self, group_id, user_id):
        user= await self.connection.find_one({'_id': user_id})
        if user:
            if group_id not in user["group_ids"]:
                await self.connection.update_one({'_id': user_id}, {"$push": {"group_ids": group_id}})
        else:
            await self.connection.insert_one({'_id': user_id, 'group_ids': [group_id]})

    async def get_connected_grps(self, user_id):
        user = await self.connection.find_one({'_id': user_id})
        if user:
            return user["group_ids"]
        else:
            return []

    async def disconnect_group(self, group_id, user_id):
        user = await self.connection.find_one({'_id': user_id})
        if user and group_id in user.get("group_ids", []):
            await self.connection.update_one(
                {'_id': user_id},
                {"$pull": {"group_ids": group_id}}
            )
            return True
        return False

    async def count_verified_users(self):
        try:
            ist_timezone = pytz.timezone('Asia/Kolkata')
            now = datetime.datetime.now(tz=ist_timezone)
            today_start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=ist_timezone)
            count = await self.users.count_documents({"last_verified": {"$gte": today_start}})
            return count
        except Exception:
            return 0

    # Force Add Feature Methods
    async def enable_forceadd(self, chat_id):
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$set': {'enabled': True}},
            upsert=True
        )
    
    async def disable_forceadd(self, chat_id):
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$set': {'enabled': False}},
            upsert=True
        )
    
    async def is_forceadd_enabled(self, chat_id):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        return doc.get('enabled', False) if doc else False
    
    async def set_forceadd_count(self, chat_id, count):
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$set': {'required_count': int(count)}},
            upsert=True
        )
    
    async def get_forceadd_count(self, chat_id):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        return doc.get('required_count', 2) if doc else 2
    
    async def get_user_add_count(self, chat_id, user_id):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        if doc and 'user_counts' in doc:
            return doc['user_counts'].get(str(user_id), 0)
        return 0
    
    async def increment_user_add_count(self, chat_id, user_id, count=1):
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$inc': {f'user_counts.{user_id}': count}},
            upsert=True
        )
    
    async def reset_all_user_add_counts(self, chat_id):
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$set': {'user_counts': {}}},
            upsert=True
        )
    
    async def reset_global_forceadd_counts(self):
        result = await self.forceadd.update_many(
            {},
            {'$set': {'user_counts': {}}}
        )
        return result.modified_count
    
    async def save_user_invite_link(self, chat_id, user_id, invite_link):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        invite_links = doc.get('invite_links_list', []) if doc else []
        invite_links = [l for l in invite_links if l.get('user_id') != int(user_id)]
        invite_links.append({'user_id': int(user_id), 'link': invite_link})
        await self.forceadd.update_one(
            {'chat_id': int(chat_id)},
            {'$set': {'invite_links_list': invite_links}},
            upsert=True
        )
    
    async def get_user_by_invite_link(self, chat_id, invite_link):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        if doc:
            if 'invite_links_list' in doc:
                for item in doc['invite_links_list']:
                    if item.get('link') == invite_link:
                        return item.get('user_id')
            if 'invite_links' in doc:
                return doc['invite_links'].get(invite_link)
        return None
    
    async def get_user_invite_link(self, chat_id, user_id):
        doc = await self.forceadd.find_one({'chat_id': int(chat_id)})
        if doc:
            if 'invite_links_list' in doc:
                for item in doc['invite_links_list']:
                    if item.get('user_id') == int(user_id):
                        return item.get('link')
            if 'invite_links' in doc:
                for link, uid in doc['invite_links'].items():
                    if uid == int(user_id):
                        return link
        return None

    async def get_maintenance_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'MAINTENANCE_MODE', MAINTENANCE_MODE)

    async def update_maintenance_status(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'MAINTENANCE_MODE', enable)

    async def pm_search_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'PM_SEARCH', PM_SEARCH)

    async def update_pm_search_status(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'PM_SEARCH', enable)

    async def movie_update_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'MOVIE_UPDATE_NOTIFICATION', MOVIE_UPDATE_NOTIFICATION)

    async def update_movie_update_status(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'MOVIE_UPDATE_NOTIFICATION', enable)

        
db = Database(DATABASE_URI, DATABASE_NAME)    
db2 = Database(DATABASE_URI2, DATABASE_NAME)
