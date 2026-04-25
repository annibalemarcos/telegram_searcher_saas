import asyncio
from datetime import datetime
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from langdetect import LangDetectException, detect
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty

logger = logging.getLogger(__name__)


def normalize_telegram_id(value: Any) -> Optional[int]:
    """Normaliza IDs do Telegram.

    Canais/supergrupos podem aparecer como 123, -100123 ou strings.
    Para comparação de pertencimento, comparamos pelo núcleo positivo.
    """
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    n = abs(n)
    s = str(n)
    if s.startswith("100") and len(s) > 5:
        s = s[3:]
    try:
        return int(s)
    except ValueError:
        return n


def clean_text_for_lang(text: str) -> str:
    return re.sub(r"[^A-Za-zÀ-ÿ\s]", "", text or "").strip()


@dataclass
class SearchFilters:
    language: str = ""          # '', 'pt', 'en', etc.
    min_members: int = 0
    max_members: Optional[int] = None
    group_type: str = "all"     # all, groups, channels
    verified_only: bool = False
    exclude_my_groups: bool = True
    limit: int = 50


@dataclass
class SearchStats:
    raw_found: int = 0
    duplicates_skipped: int = 0
    no_username_skipped: int = 0
    my_groups_loaded: int = 0
    my_groups_removed: int = 0
    filters_removed: int = 0
    returned: int = 0
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__


class TelegramGroupSearcherWeb:
    def __init__(self, api_id: int, api_hash: str, phone_number: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number.strip()
        session_name = "session_" + re.sub(r"[^0-9A-Za-z_]+", "_", self.phone_number)
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.my_group_ids: Set[int] = set()
        self.stats = SearchStats()

    async def connect(self) -> bool:
        try:
            await self.client.start(phone=self.phone_number)
            await self.load_my_dialog_ids()
            return True
        except Exception as exc:
            logger.exception("Erro ao conectar no Telegram")
            self.stats.warnings.append(f"Erro ao conectar: {exc}")
            return False

    async def disconnect(self) -> None:
        try:
            await self.client.disconnect()
        except Exception:
            pass

    async def load_my_dialog_ids(self) -> None:
        self.my_group_ids.clear()
        try:
            async for dialog in self.client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    nid = normalize_telegram_id(dialog.id)
                    if nid is not None:
                        self.my_group_ids.add(nid)
                    entity = getattr(dialog, "entity", None)
                    nid2 = normalize_telegram_id(getattr(entity, "id", None))
                    if nid2 is not None:
                        self.my_group_ids.add(nid2)
        except Exception as exc:
            self.stats.warnings.append(f"Não consegui carregar seus grupos atuais: {exc}")
        self.stats.my_groups_loaded = len(self.my_group_ids)

    def _entity_type(self, entity: Any) -> str:
        if getattr(entity, "megagroup", False):
            return "supergroup"
        if getattr(entity, "broadcast", False):
            return "channel"
        return "group"

    def _group_info(self, entity: Any, method: str) -> Optional[Dict[str, Any]]:
        username = getattr(entity, "username", None)
        if not username:
            self.stats.no_username_skipped += 1
            return None
        raw_id = getattr(entity, "id", None)
        normalized_id = normalize_telegram_id(raw_id)
        return {
            "id": raw_id,
            "normalized_id": normalized_id,
            "title": getattr(entity, "title", "Sem título") or "Sem título",
            "username": username,
            "participants_count": getattr(entity, "participants_count", 0) or 0,
            "type": self._entity_type(entity),
            "verified": bool(getattr(entity, "verified", False)),
            "description": getattr(entity, "about", "") or "",
            "method": method,
            "link": f"https://t.me/{username}",
            "is_mine": normalized_id in self.my_group_ids if normalized_id is not None else False,
        }

    def _is_language(self, group: Dict[str, Any], lang_code: str) -> bool:
        text = clean_text_for_lang((group.get("title", "") + " " + group.get("description", "")).strip())
        if len(text) < 20:
            # Não mate resultado por texto curto. Esse era um assassino silencioso.
            return True
        try:
            return detect(text) == lang_code
        except LangDetectException:
            return True

    def _passes_filters(self, group: Dict[str, Any], filters: SearchFilters) -> Tuple[bool, str]:
        if filters.exclude_my_groups and group.get("is_mine"):
            return False, "my_group"

        members = int(group.get("participants_count") or 0)
        if filters.min_members and members < filters.min_members:
            return False, "min_members"
        if filters.max_members is not None and members > filters.max_members:
            return False, "max_members"

        gtype = group.get("type", "channel")
        if filters.group_type == "groups" and gtype not in {"group", "supergroup"}:
            return False, "type"
        if filters.group_type == "channels" and gtype != "channel":
            return False, "type"

        if filters.verified_only and not group.get("verified"):
            return False, "verified"

        if filters.language and not self._is_language(group, filters.language):
            return False, "language"

        return True, "ok"

    async def search(self, keyword: str, filters: SearchFilters) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        keyword = (keyword or "").strip()
        if not keyword:
            return [], self.stats.as_dict()

        seen: Set[int] = set()
        groups: List[Dict[str, Any]] = []

        def add_entity(entity: Any, method: str) -> None:
            info = self._group_info(entity, method)
            if not info:
                return
            nid = info.get("normalized_id")
            if nid is None:
                return
            if nid in seen:
                self.stats.duplicates_skipped += 1
                return
            seen.add(nid)
            groups.append(info)

        # 1) Busca global de mensagens públicas. Costuma achar canais/grupos fora dos seus diálogos.
        try:
            result = await self.client(SearchGlobalRequest(
                q=keyword,
                filter=InputMessagesFilterEmpty(),
                min_date=datetime(2000, 1, 1),
                max_date=datetime.now(),
                limit=max(10, min(filters.limit, 100)),
                offset_rate=0,
                offset_peer=InputPeerEmpty(),
                offset_id=0,
            ))
            for chat in getattr(result, "chats", []) or []:
                add_entity(chat, "global_messages")
        except Exception as exc:
            self.stats.warnings.append(f"Busca global falhou: {exc}")

        # 2) Busca pública por contatos/chats.
        try:
            result = await self.client(SearchRequest(q=keyword, limit=max(10, min(filters.limit, 100))))
            for chat in getattr(result, "chats", []) or []:
                add_entity(chat, "contacts_search")
        except Exception as exc:
            self.stats.warnings.append(f"Busca pública falhou: {exc}")

        # 3) Variações de username — útil para termos como 'dua lipa', 'puxadas br' etc.
        variations = []
        base = keyword.strip().lstrip("@")
        if len(base) >= 3:
            compact = re.sub(r"\s+", "", base)
            underscored = re.sub(r"\s+", "_", base)
            variations = [base, compact, underscored, f"{compact}br", f"{underscored}_br", f"{compact}brasil", f"{underscored}_brasil", f"{compact}oficial"]
        for username in dict.fromkeys(variations):
            try:
                entity = await self.client.get_entity(username)
                if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                    add_entity(entity, "username_variation")
            except Exception:
                continue

        self.stats.raw_found = len(groups)

        filtered: List[Dict[str, Any]] = []
        for group in groups:
            ok, reason = self._passes_filters(group, filters)
            if ok:
                filtered.append(group)
            else:
                if reason == "my_group":
                    self.stats.my_groups_removed += 1
                else:
                    self.stats.filters_removed += 1

        filtered.sort(key=lambda g: (g.get("participants_count") or 0, bool(g.get("verified"))), reverse=True)
        self.stats.returned = len(filtered)
        return filtered[: filters.limit], self.stats.as_dict()


async def run_telegram_search(api_id: int, api_hash: str, phone: str, keyword: str, filters: SearchFilters):
    searcher = TelegramGroupSearcherWeb(api_id, api_hash, phone)
    if not await searcher.connect():
        return [], searcher.stats.as_dict()
    try:
        return await searcher.search(keyword, filters)
    finally:
        await searcher.disconnect()
