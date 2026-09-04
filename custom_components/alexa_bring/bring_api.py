"""Bring! API Client (Async) for Home Assistant."""
from __future__ import annotations

import logging
import json
import os
import asyncio
import uuid
import aiohttp
from typing import Any

from .const import API_BASE, API_KEY, CLIENT, APPLICATION, COUNTRY

_LOGGER = logging.getLogger(__name__)

class BringAPI:
    """Async Bring! API Client."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str, list_name: str, cache_dir: str) -> None:
        self.session = session
        self.email = email
        self.password = password
        self.list_name = list_name
        self.cache_dir = cache_dir
        
        self.auth_data: dict[str, Any] = {}
        self.list_uuid: str | None = None
        self.catalog_cache: list[str] = []
        self.details_cache: dict[str, dict[str, Any]] = {}
        self.catalog_sections: dict[str, tuple[str, str]] = {}
        
        self._cache_file = os.path.join(self.cache_dir, "bring_auth_cache.json")
        self._catalog_file = os.path.join(self.cache_dir, "bring_catalog_cache.json")
        self._catalog_sections_file = os.path.join(self.cache_dir, "bring_catalog_sections_cache.json")

    def _get_headers(self) -> dict[str, str]:
        headers = {
            'X-BRING-API-KEY': API_KEY,
            'X-BRING-CLIENT': CLIENT,
            'X-BRING-APPLICATION': APPLICATION,
            'X-BRING-COUNTRY': COUNTRY,
            'Content-Type': 'application/json'
        }
        if self.auth_data:
            headers['Authorization'] = f"{self.auth_data.get('token_type', 'Bearer')} {self.auth_data.get('access_token')}"
            headers['X-BRING-USER-UUID'] = self.auth_data.get('uuid', '')
            headers['X-BRING-PUBLIC-USER-UUID'] = self.auth_data.get('publicUuid', '')
        return headers

    async def authenticate(self) -> bool:
        """Authenticate with Bring! API."""
        if os.path.exists(self._cache_file):
            try:
                def _load():
                    with open(self._cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                cached = await asyncio.to_thread(_load)
                if cached and cached.get('access_token'):
                    self.auth_data = cached
                    return True
            except Exception:
                pass

        headers = {
            'X-BRING-API-KEY': API_KEY,
            'X-BRING-CLIENT': CLIENT,
            'X-BRING-APPLICATION': APPLICATION,
            'X-BRING-COUNTRY': COUNTRY,
        }
        
        try:
            async with self.session.post(f"{API_BASE}/v2/bringauth", data={'email': self.email, 'password': self.password}, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.auth_data = {
                        'access_token': data.get('access_token'),
                        'token_type': data.get('token_type', 'Bearer'),
                        'uuid': data.get('uuid') or data.get('userUuid', ''),
                        'publicUuid': data.get('publicUuid') or data.get('uuid', ''),
                        'bringListUUID': data.get('bringListUUID', '')
                    }
                    def _save():
                        os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
                        with open(self._cache_file, 'w', encoding='utf-8') as f:
                            json.dump(self.auth_data, f, ensure_ascii=False)
                    await asyncio.to_thread(_save)
                    return True
                else:
                    _LOGGER.error("Bring! Authentication failed: %s", resp.status)
                    return False
        except Exception as e:
            _LOGGER.error("Bring! Authentication error: %s", str(e))
            return False

    async def get_list_uuid(self) -> str:
        """Get the UUID of the target list."""
        if self.list_uuid:
            return self.list_uuid
            
        if self.auth_data.get('bringListUUID') and (not self.list_name or self.list_name.lower() in ['einkaufsliste', 'einkauf']):
            self.list_uuid = self.auth_data['bringListUUID']
            return self.list_uuid

        try:
            url = f"{API_BASE}/bringusers/{self.auth_data['uuid']}/lists"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lists = data.get('lists', [])
                    for lst in lists:
                        if lst.get('name', '').lower() == self.list_name.lower():
                            self.list_uuid = lst.get('listUuid')
                            return self.list_uuid
                    if lists:
                        self.list_uuid = lists[0].get('listUuid')
                        return self.list_uuid
        except Exception as e:
            _LOGGER.error("Error getting list UUID: %s", str(e))
            
        self.list_uuid = self.auth_data.get('bringListUUID')
        return self.list_uuid

    async def get_catalog(self) -> list[str]:
        """Fetch the list catalog (standard master items and custom items)."""
        if self.catalog_cache:
            return self.catalog_cache
            
        if os.path.exists(self._catalog_file):
            try:
                def _load():
                    with open(self._catalog_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                cached = await asyncio.to_thread(_load)
                if cached:
                    self.catalog_cache = cached
                    return self.catalog_cache
            except Exception:
                pass

        master_items: list[str] = []
        try:
            sections = await self.get_catalog_sections()
            master_items = [v[0] for v in sections.values() if isinstance(v, (list, tuple))]
        except Exception as e:
            _LOGGER.warning("Could not fetch master catalog items: %s", e)

        custom_items: list[str] = []
        list_uuid = await self.get_list_uuid()
        if list_uuid:
            try:
                url = f"{API_BASE}/v2/bringlists/{list_uuid}/details"
                async with self.session.get(url, headers=self._get_headers()) as resp:
                    if resp.status == 200:
                        items = await resp.json()
                        custom_items = [i.get('itemId') for i in items if i.get('itemId')]
            except Exception as e:
                _LOGGER.error("Error fetching list details: %s", str(e))

        combined = list(dict.fromkeys(master_items + custom_items))
        if combined:
            self.catalog_cache = combined
            def _save():
                os.makedirs(os.path.dirname(self._catalog_file), exist_ok=True)
                with open(self._catalog_file, 'w', encoding='utf-8') as f:
                    json.dump(self.catalog_cache, f, ensure_ascii=False)
            await asyncio.to_thread(_save)
            return self.catalog_cache

        return master_items or custom_items

    async def get_active_items(self) -> list[dict[str, str]]:
        """Fetch active (purchase) items from the list."""
        list_uuid = await self.get_list_uuid()
        if not list_uuid:
            return []

        url = f"{API_BASE}/v2/bringlists/{list_uuid}"
        try:
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 401:
                    # Token expired, retry
                    if os.path.exists(self._cache_file):
                        os.remove(self._cache_file)
                    await self.authenticate()
                    async with self.session.get(url, headers=self._get_headers()) as resp2:
                        if resp2.status == 200:
                            data = await resp2.json()
                        else:
                            return []
                elif resp.status == 200:
                    data = await resp.json()
                else:
                    return []
                    
            raw_purchase = data.get('purchase') or (data.get('items', {}).get('purchase') if isinstance(data.get('items'), dict) else []) or []
            return raw_purchase
        except Exception as e:
            _LOGGER.error("Error fetching active items: %s", str(e))
            return []

    async def execute_batch_changes(self, changes: list[dict[str, Any]]) -> bool:
        """Send batch changes (add/remove) to Bring!."""
        if not changes:
            return True
            
        list_uuid = await self.get_list_uuid()
        if not list_uuid:
            return False

        payload = {"changes": changes, "sender": ""}
        url = f"{API_BASE}/v2/bringlists/{list_uuid}/items"
        
        try:
            async with self.session.put(url, json=payload, headers=self._get_headers()) as resp:
                if resp.status == 401:
                    if os.path.exists(self._cache_file):
                        os.remove(self._cache_file)
                    await self.authenticate()
                    async with self.session.put(url, json=payload, headers=self._get_headers()) as resp2:
                        return resp2.status == 200
                return resp.status == 200
        except Exception as e:
            _LOGGER.error("Error executing changes: %s", str(e))
            return False

    async def get_catalog_sections(self) -> dict[str, tuple[str, str]]:
        """Fetch Bring! catalog sections and item mapping: {itemId_lower: (itemId, sectionName)}."""
        if self.catalog_sections:
            return self.catalog_sections

        if os.path.exists(self._catalog_sections_file):
            try:
                def _load():
                    with open(self._catalog_sections_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                cached = await asyncio.to_thread(_load)
                if cached:
                    self.catalog_sections = cached
                    return self.catalog_sections
            except Exception:
                pass

        url = "https://web.getbring.com/locale/catalog.de-DE.json"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cat = data.get('catalog', {})
                    mapping = {}
                    for s in cat.get('sections', []):
                        s_name = s.get('name')
                        for item in s.get('items', []):
                            i_name = item.get('itemId') or item.get('name')
                            if i_name and s_name:
                                mapping[i_name.lower()] = [i_name, s_name]
                    if mapping:
                        self.catalog_sections = mapping
                        def _save():
                            os.makedirs(os.path.dirname(self._catalog_sections_file), exist_ok=True)
                            with open(self._catalog_sections_file, 'w', encoding='utf-8') as f:
                                json.dump(self.catalog_sections, f, ensure_ascii=False)
                        await asyncio.to_thread(_save)
                        return self.catalog_sections
        except Exception as e:
            _LOGGER.warning("Could not fetch Bring! catalog sections: %s", e)

        return self.catalog_sections

    async def get_item_details_map(self) -> dict[str, dict[str, Any]]:
        """Fetch custom item details (icons, sections) for the list."""
        list_uuid = await self.get_list_uuid()
        if not list_uuid:
            return {}

        url = f"{API_BASE}/v2/bringlists/{list_uuid}/details"
        try:
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    details = await resp.json()
                    det_map = {}
                    for d in details:
                        item_id = d.get('itemId')
                        if item_id:
                            det_map[item_id.lower()] = d
                            det_map[item_id] = d
                    self.details_cache = det_map
                    return self.details_cache
        except Exception as e:
            _LOGGER.error("Error fetching item details: %s", str(e))
        return self.details_cache

    async def save_item_detail(self, item_id: str, icon_item_id: str, section_id: str) -> bool:
        """Assign icon and section/category to an item via Bring! detail API."""
        list_uuid = await self.get_list_uuid()
        if not list_uuid or not item_id or not icon_item_id:
            return False

        url = f"{API_BASE}/v2/bringlistitemdetails/"
        b_id = f"----bring-{uuid.uuid4()}"
        payload = {
            'listUuid': list_uuid,
            'itemId': item_id,
            'userIconItemId': icon_item_id,
            'userSectionId': section_id or '',
            'assignedTo': ''
        }

        chunks = []
        for k, v in payload.items():
            chunks.append(f'--{b_id}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
        chunks.append(f'--{b_id}--\r\n'.encode('utf-8'))
        body_bytes = b"".join(chunks)

        headers = self._get_headers()
        headers['Content-Type'] = f'multipart/form-data; boundary={b_id}'

        try:
            async with self.session.post(url, data=body_bytes, headers=headers) as resp:
                if resp.status in (200, 201):
                    _LOGGER.info("Successfully assigned detail for '%s': icon='%s', section='%s'", item_id, icon_item_id, section_id)
                    self.details_cache[item_id.lower()] = {
                        'itemId': item_id,
                        'userIconItemId': icon_item_id,
                        'userSectionId': section_id
                    }
                    self.details_cache[item_id] = self.details_cache[item_id.lower()]
                    return True
                else:
                    _LOGGER.error("Failed to assign detail for '%s', status: %s", item_id, resp.status)
                    return False
        except Exception as e:
            _LOGGER.error("Error saving detail for '%s': %s", item_id, str(e))
            return False

    async def delete_item_detail(self, detail_uuid: str) -> bool:
        """Delete a custom item detail from Bring! by its UUID."""
        if not detail_uuid:
            return False
        url = f"{API_BASE}/v2/bringlistitemdetails/{detail_uuid}"
        h = self._get_headers()
        headers = {k: v for k, v in h.items() if k != 'Content-Type'}
        try:
            async with self.session.delete(url, headers=headers) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            _LOGGER.error("Error deleting detail %s: %s", detail_uuid, str(e))
            return False


