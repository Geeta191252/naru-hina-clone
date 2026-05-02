from motor.motor_asyncio import AsyncIOMotorClient
from info import DATABASE_URI
from datetime import datetime
import os
from logging_helper import LOGGER

# Free tier 512 MB. Cleanup the user-messages collection when above this.
TOPDB_CLEANUP_THRESHOLD_MB = int(os.environ.get('TOPDB_CLEANUP_THRESHOLD_MB', '480'))
TOPDB_CLEANUP_BATCH = int(os.environ.get('TOPDB_CLEANUP_BATCH', '1000'))


class Database:
    def __init__(self, uri, db_name):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.col = self.db.user

    async def _db_size_mb(self):
        try:
            stats = await self.db.command("dbstats")
            return stats.get('dataSize', 0) / 1024 / 1024
        except Exception:
            return 0

    async def _auto_cleanup(self):
        """If DB above threshold, delete oldest user docs to free space."""
        try:
            size_mb = await self._db_size_mb()
            if size_mb < TOPDB_CLEANUP_THRESHOLD_MB:
                return 0
            LOGGER.warning(f"[TOPDB-CLEANUP] size {size_mb:.1f} MB >= {TOPDB_CLEANUP_THRESHOLD_MB} MB. Cleaning oldest user docs...")
            total_deleted = 0
            for _ in range(20):
                cursor = self.col.find({}, {'_id': 1}).sort('$natural', 1).limit(TOPDB_CLEANUP_BATCH)
                ids = [doc['_id'] async for doc in cursor]
                if not ids:
                    break
                res = await self.col.delete_many({'_id': {'$in': ids}})
                total_deleted += res.deleted_count
                size_mb = await self._db_size_mb()
                LOGGER.warning(f"[TOPDB-CLEANUP] deleted {res.deleted_count}. New size: {size_mb:.1f} MB")
                if size_mb < TOPDB_CLEANUP_THRESHOLD_MB:
                    break
            try:
                await self.db.command({'compact': 'user'})
            except Exception:
                pass
            LOGGER.warning(f"[TOPDB-CLEANUP] total deleted = {total_deleted}")
            return total_deleted
        except Exception as e:
            LOGGER.error(f"[TOPDB-CLEANUP] failed: {e}")
            return 0

    async def update_top_messages(self, user_id, message_text):
        try:
            user = await self.col.find_one({"user_id": user_id, "messages.text": message_text})
            if not user:
                await self.col.update_one(
                    {"user_id": user_id},
                    {"$push": {"messages": {"text": message_text, "count": 1}}},
                    upsert=True
                )
            else:
                await self.col.update_one(
                    {"user_id": user_id, "messages.text": message_text},
                    {"$inc": {"messages.$.count": 1}}
                )
        except Exception as e:
            # NEVER let this break movie search. If quota full → cleanup + swallow.
            msg = str(e).lower()
            LOGGER.error(f"[TOPDB] update_top_messages failed: {e}")
            if 'space quota' in msg or 'over your space' in msg or 'quota' in msg:
                try:
                    await self._auto_cleanup()
                except Exception as ce:
                    LOGGER.error(f"[TOPDB] cleanup after quota error failed: {ce}")
            return

    async def get_top_messages(self, limit=30):
        try:
            pipeline = [
                {"$unwind": "$messages"},
                {"$group": {"_id": "$messages.text", "count": {"$sum": "$messages.count"}}},
                {"$sort": {"count": -1}},
                {"$limit": limit}
            ]
            results = await self.col.aggregate(pipeline).to_list(limit)
            return [result['_id'] for result in results]
        except Exception as e:
            LOGGER.error(f"[TOPDB] get_top_messages failed: {e}")
            return []

    async def delete_all_messages(self):
        try:
            await self.col.delete_many({})
        except Exception as e:
            LOGGER.error(f"[TOPDB] delete_all_messages failed: {e}")

    async def auto_cleanup(self):
        return await self._auto_cleanup()


silentdb = Database(DATABASE_URI, "SilentXBotz")
