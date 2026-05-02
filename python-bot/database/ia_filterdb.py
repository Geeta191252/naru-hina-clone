from struct import pack
import re
import base64
from typing import Dict, List
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import *
from utils import get_settings, save_group_settings
from collections import defaultdict
from datetime import datetime, timedelta
from logging_helper import LOGGER


client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

client2 = AsyncIOMotorClient(DATABASE_URI2)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)

client3 = AsyncIOMotorClient(DATABASE_URI3)
db3 = client3[DATABASE_NAME]
instance3 = Instance.from_db(db3)


@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

@instance2.register
class Media2(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

@instance3.register
class Media3(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

async def check_db_size(silentdb):
    return (await silentdb.command("dbstats"))['dataSize']


# ===== AUTO CLEANUP: Delete oldest files when DB is near full =====
# Atlas free tier = 512 MB. Cleanup trigger threshold (default 480 MB)
# ===== AUTO CLEANUP: Delete oldest files when DB is near full =====
# Atlas free tier = 512 MB. Cleanup trigger threshold (default 480 MB)
import os as _os
DB_CLEANUP_THRESHOLD_MB = int(_os.environ.get('DB_CLEANUP_THRESHOLD_MB', '480'))
DB_CLEANUP_BATCH = int(_os.environ.get('DB_CLEANUP_BATCH', '500'))  # delete 500 oldest at a time

async def _cleanup_collection(silentdb, collection_name, label):
    """Delete oldest documents from a collection until size drops below threshold."""
    try:
        threshold_bytes = DB_CLEANUP_THRESHOLD_MB * 1024 * 1024
        size = await check_db_size(silentdb)
        if size < threshold_bytes:
            return 0
        LOGGER.warning(f"[AUTO-CLEANUP] {label} DB size {size/1024/1024:.1f} MB >= {DB_CLEANUP_THRESHOLD_MB} MB. Cleaning oldest files...")
        coll = silentdb[collection_name]
        total_deleted = 0
        # loop until under threshold or nothing left
        for _ in range(20):  # safety cap: max 10k files per run
            # Oldest = lowest _id (ObjectId is time-ordered, but our _id is file_id string).
            # Use $natural order ascending = insertion order.
            cursor = coll.find({}, {'_id': 1}).sort('$natural', 1).limit(DB_CLEANUP_BATCH)
            ids = [doc['_id'] async for doc in cursor]
            if not ids:
                break
            res = await coll.delete_many({'_id': {'$in': ids}})
            total_deleted += res.deleted_count
            new_size = await check_db_size(silentdb)
            LOGGER.warning(f"[AUTO-CLEANUP] {label}: deleted {res.deleted_count} files. New size: {new_size/1024/1024:.1f} MB")
            if new_size < threshold_bytes:
                break
        # try compact to reclaim space (best-effort, may not work on shared tiers)
        try:
            await silentdb.command({'compact': collection_name})
        except Exception:
            pass
        LOGGER.warning(f"[AUTO-CLEANUP] {label}: total deleted = {total_deleted}")
        return total_deleted
    except Exception as e:
        LOGGER.error(f"[AUTO-CLEANUP] {label} failed: {e}")
        return 0

async def auto_cleanup_dbs():
    """Run cleanup on all 3 DBs if needed. Safe to call repeatedly."""
    deleted = 0
    deleted += await _cleanup_collection(db, COLLECTION_NAME, "Primary")
    if MULTIPLE_DB:
        try:
            deleted += await _cleanup_collection(db2, COLLECTION_NAME, "Secondary")
        except Exception as e:
            LOGGER.error(f"[AUTO-CLEANUP] Secondary error: {e}")
        try:
            deleted += await _cleanup_collection(db3, COLLECTION_NAME, "Third")
        except Exception as e:
            LOGGER.error(f"[AUTO-CLEANUP] Third error: {e}")
    return deleted


async def save_file(media):
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"[_\-\.#+$%^&*()!~`,;:\"'?/<>\[\]{}=|\\]", " ", str(media.file_name))
    file_name = re.sub(r"\s+", " ", file_name).strip()    
    primary_db_size = await check_db_size(db)
    db_change_limit_bytes = DB_CHANGE_LIMIT * 1024 * 1024
    db_used = "Primary"
    saveMedia = Media
    exists_in_primary = await Media.count_documents({'file_id': file_id}, limit=1)
    if exists_in_primary:
        LOGGER.info(f'{file_name} Is Already Saved In Primary Database!')
        return False, 0
        
    if MULTIPLE_DB and primary_db_size >= db_change_limit_bytes:
        LOGGER.info("Primary Database Is Low On Space. Switching To Secondary DB.")
        saveMedia = Media2
        db_used = "Secondary"
        exists_in_secondary = await Media2.count_documents({'file_id': file_id}, limit=1)
        if exists_in_secondary:
            LOGGER.info(f'{file_name} Is Already Saved In Secondary Database!')
            return False, 0
        # Check secondary db size, if full switch to third
        secondary_db_size = await check_db_size(db2)
        if secondary_db_size >= db_change_limit_bytes:
            LOGGER.info("Secondary Database Is Low On Space. Switching To Third DB.")
            saveMedia = Media3
            db_used = "Third"
            exists_in_third = await Media3.count_documents({'file_id': file_id}, limit=1)
            if exists_in_third:
                LOGGER.info(f'{file_name} Is Already Saved In Third Database!')
                return False, 0
            
    try:
        file = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError as e:
        LOGGER.error(f'Validation Error While Saving File: {e}')
        return False, 2
    else:
        try:
            await file.commit()
        except DuplicateKeyError:
            LOGGER.error(f'{file_name} Is Already Saved In {db_used} Database')
            return False, 0
        else:
            LOGGER.info(f'{file_name} Saved Successfully In {db_used} Database')
            return True, 1
            

async def get_search_results(chat_id, query, file_type=None, max_results=10, offset=0, filter=False):
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        try:
            max_results = 10 if settings.get('max_btn') else int(MAX_B_TN)
        except KeyError:
            await save_group_settings(int(chat_id), 'max_btn', False)
            settings = await get_settings(int(chat_id))
            max_results = 10 if settings.get('max_btn') else int(MAX_B_TN)

    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        raw_pattern = query.replace(" ", r".*[\s\.\+\-_()\[\]]")

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []
    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    total_results = await Media.count_documents(filter)
    if MULTIPLE_DB:
        total_results += await Media2.count_documents(filter)
        total_results += await Media3.count_documents(filter)
    if max_results % 2 != 0:
        logger.info(f"Since max_results Is An Odd Number ({max_results}), Bot Will Use {max_results + 1} As max_results To Make It Even.")
        max_results += 1
    cursor1 = Media.find(filter).sort('$natural', -1).skip(offset).limit(max_results)
    files1 = await cursor1.to_list(length=max_results)
    if MULTIPLE_DB:
        remaining_results = max_results - len(files1)
        cursor2 = Media2.find(filter).sort('$natural', -1).skip(offset).limit(remaining_results)
        files2 = await cursor2.to_list(length=remaining_results)
        files = files1 + files2
        remaining_results = max_results - len(files)
        if remaining_results > 0:
            cursor3 = Media3.find(filter).sort('$natural', -1).skip(offset).limit(remaining_results)
            files3 = await cursor3.to_list(length=remaining_results)
            files = files + files3
    else:
        files = files1
    next_offset = offset + len(files)
    if next_offset >= total_results:
        next_offset = ''
    return files, next_offset, total_results
    
async def get_bad_files(query, file_type=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        raw_pattern = query.replace(" ", r".*[\s\.\+\-_()]")
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []
    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    cursor1 = Media.find(filter).sort('$natural', -1)
    files1 = await cursor1.to_list(length=(await Media.count_documents(filter)))
    if MULTIPLE_DB:
        cursor2 = Media2.find(filter).sort('$natural', -1)
        files2 = await cursor2.to_list(length=(await Media2.count_documents(filter)))
        cursor3 = Media3.find(filter).sort('$natural', -1)
        files3 = await cursor3.to_list(length=(await Media3.count_documents(filter)))
        files = files1 + files2 + files3
    else:
        files = files1
    total_results = len(files)
    return files, total_results
    

async def get_file_details(query):
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    if not filedetails:
        cursor2 = Media2.find(filter)
        filedetails = await cursor2.to_list(length=1)
    if not filedetails:
        cursor3 = Media3.find(filter)
        filedetails = await cursor3.to_list(length=1)
    return filedetails


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref

async def siletxbotz_fetch_media(limit: int) -> List[dict]:
    try:
        if MULTIPLE_DB:
            db_size = await check_db_size(Media)
            if db_size > DB_CHANGE_LIMIT:
                cursor = Media2.find().sort("$natural", -1).limit(limit)
                files = await cursor.to_list(length=limit)
                return files
        cursor = Media.find().sort("$natural", -1).limit(limit)
        files = await cursor.to_list(length=limit)
        return files
    except Exception as e:
        LOGGER.error(f"Error in siletxbotz_fetch_media: {e}")
        return []

async def silentxbotz_clean_title(filename: str, is_series: bool = False) -> str:
    try:
        year_match = re.search(r"^(.*?(\d{4}|\(\d{4}\)))", filename, re.IGNORECASE)
        if year_match:
            title = year_match.group(1).replace('(', '').replace(')', '') 
            return re.sub(r"[._\-\[\]@()]+", " ", title).strip().title()
        if is_series:
            season_match = re.search(r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))(?:\s*Combined)?", filename, re.IGNORECASE)
            if season_match:
                title = season_match.group(1).strip()
                season = season_match.group(2) or season_match.group(3) or season_match.group(4)
                title = re.sub(r"[._\-\[\]@()]+", " ", title).strip().title()
                return f"{title} S{int(season):02}"
        return re.sub(r"[._\-\[\]@()]+", " ", filename).strip().title()
    except Exception as e:
        LOGGER.error(f"Error in truncate_title: {e}")
        return filename
        
async def siletxbotz_get_movies(limit: int = 20) -> List[str]:
    try:
        cursor = await siletxbotz_fetch_media(limit * 2)
        results = set()
        pattern = r"(?:s\d{1,2}|season\s*\d+|season\d+)(?:\s*combined)?(?:e\d{1,2}|episode\s*\d+)?\b"
        for file in cursor:
            file_name = getattr(file, "file_name", "")
            caption = getattr(file, "caption", "")
            if not (re.search(pattern, file_name, re.IGNORECASE) or re.search(pattern, caption, re.IGNORECASE)):
                title = await silentxbotz_clean_title(file_name)
                results.add(title)
            if len(results) >= limit:
                break
        return sorted(list(results))[:limit]
    except Exception as e:
        LOGGER.error(f"Error in siletxbotz_get_movies: {e}")
        return []

async def siletxbotz_get_series(limit: int = 30) -> Dict[str, List[int]]:
    try:
        cursor = await siletxbotz_fetch_media(limit * 5)
        grouped = defaultdict(list)
        pattern = r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))(?:\s*Combined)?(?:E(\d{1,2})|Episode\s*(\d+))?\b"
        for file in cursor:
            file_name = getattr(file, "file_name", "")
            caption = getattr(file, "caption", "")
            match = None
            if file_name:
                match = re.search(pattern, file_name, re.IGNORECASE)
            if not match and caption:
                match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                title = await silentxbotz_clean_title(match.group(1), is_series=True)
                season = int(match.group(2) or match.group(3) or match.group(4))
                grouped[title].append(season)
        return {title: sorted(set(seasons))[:10] for title, seasons in grouped.items() if seasons}
    except Exception as e:
        LOGGER.error(f"Error in siletxbotz_get_series: {e}")
        return []
