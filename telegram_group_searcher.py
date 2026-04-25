import asyncio
import re
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty
import logging

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None
    class LangDetectException(Exception):
        pass

API_ID = 20041297
API_HASH = "ba389b89510d524e1f62da82cc24c266"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_peer_id(value):
    """
    Normaliza IDs para comparar grupo/canal visto como 123, -100123 ou similares.
    """
    try:
        raw = str(value).replace("-100", "").replace("-", "")
        return int(raw)
    except Exception:
        return value


class TelegramGroupSearcher:
    def __init__(self, api_id, api_hash, phone_number):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        safe_phone = re.sub(r"[^0-9A-Za-z_]+", "_", phone_number or "default")
        self.client = TelegramClient(f"session_{safe_phone}", api_id, api_hash)
        self.my_group_ids = set()
        self.debug_warnings = []

        self.filters = {
            "language": None,
            "min_members": 0,
            "max_members": None,
            "group_type": "all",
            "verified_only": False,
            "exclude_my_groups": True,
        }

    async def get_my_dialog_ids(self):
        logger.info("Carregando grupos/canais atuais para exclusão...")
        async for dialog in self.client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                self.my_group_ids.add(normalize_peer_id(dialog.id))
                entity = getattr(dialog, "entity", None)
                if entity is not None and hasattr(entity, "id"):
                    self.my_group_ids.add(normalize_peer_id(entity.id))
        logger.info(f"{len(self.my_group_ids)} grupos/canais atuais indexados para exclusão.")

    async def connect(self):
        try:
            await self.client.start(phone=self.phone_number)
            await self.get_my_dialog_ids()
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar: {e}")
            self.debug_warnings.append(f"Erro ao conectar: {e}")
            return False

    def is_language(self, group_info, lang_code="pt"):
        if not detect:
            return False

        text_to_check = (group_info.get("title", "") + " " + group_info.get("description", "")).strip()
        if not text_to_check:
            return False

        text_to_check = re.sub(r"[^A-Za-zÀ-ÿ\s]", "", text_to_check)
        if len(text_to_check) < 20:
            return False

        try:
            return detect(text_to_check) == lang_code
        except LangDetectException:
            return False

    async def apply_filters(self, groups):
        filtered_groups = []

        for group in groups:
            normalized_id = normalize_peer_id(group.get("id"))

            if self.filters["exclude_my_groups"] and normalized_id in self.my_group_ids:
                continue

            participants = group.get("participants_count", 0) or 0
            if self.filters["min_members"] and participants < self.filters["min_members"]:
                continue
            if self.filters["max_members"] and participants > self.filters["max_members"]:
                continue

            group_type = group.get("type", "channel")
            if self.filters["group_type"] == "groups" and "group" not in group_type:
                continue
            if self.filters["group_type"] == "channels" and group_type != "channel":
                continue

            if self.filters["verified_only"] and not group.get("verified", False):
                continue

            if self.filters["language"] and not self.is_language(group, self.filters["language"]):
                continue

            filtered_groups.append(group)

        return filtered_groups

    def _create_group_info_dict(self, entity, method):
        group_type = "channel"
        if getattr(entity, "megagroup", False):
            group_type = "supergroup"
        elif hasattr(entity, "broadcast") and not getattr(entity, "broadcast", True):
            group_type = "group"

        return {
            "id": normalize_peer_id(getattr(entity, "id", "")),
            "title": getattr(entity, "title", "") or "",
            "username": getattr(entity, "username", None),
            "participants_count": getattr(entity, "participants_count", 0) or 0,
            "type": group_type,
            "verified": getattr(entity, "verified", False),
            "description": getattr(entity, "about", "") or "",
            "method": method,
        }

    async def search_groups(self, keyword, limit=50):
        groups = []
        seen_ids = set()

        def add_group(entity, method):
            entity_id = normalize_peer_id(getattr(entity, "id", None))
            username = getattr(entity, "username", None)
            if entity_id and entity_id not in seen_ids and username:
                groups.append(self._create_group_info_dict(entity, method))
                seen_ids.add(entity_id)

        try:
            result = await self.client(SearchGlobalRequest(
                q=keyword,
                filter=InputMessagesFilterEmpty(),
                min_date=datetime(2000, 1, 1),
                max_date=datetime.now(),
                limit=limit,
                offset_rate=0,
                offset_peer=InputPeerEmpty(),
                offset_id=0,
            ))
            for chat in getattr(result, "chats", []):
                add_group(chat, "global_messages_chats")
        except Exception as e:
            msg = f"Busca global falhou: {e}"
            logger.warning(msg)
            self.debug_warnings.append(msg)

        try:
            result = await self.client(SearchRequest(q=keyword, limit=limit))
            for chat in getattr(result, "chats", []):
                add_group(chat, "contacts_search")
        except Exception as e:
            msg = f"Busca por contatos/chats falhou: {e}"
            logger.warning(msg)
            self.debug_warnings.append(msg)

        if len(keyword) > 3:
            variations = [keyword.replace(" ", "_"), keyword.replace(" ", "")]
            if self.filters.get("language") == "pt":
                variations.extend([f"{keyword}_br", f"{keyword}_brasil", f"{keyword}oficial"])

            for variation in variations:
                try:
                    entity = await self.client.get_entity(variation.lstrip("@"))
                    if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                        add_group(entity, "variation_search")
                except Exception:
                    continue

        groups.sort(key=lambda x: x.get("participants_count", 0), reverse=True)
        return groups

    async def disconnect(self):
        await self.client.disconnect()
