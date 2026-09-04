"""Bring! API Client (Async) for Home Assistant."""
import logging
import json
import os
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional

from .const import API_BASE, API_KEY, CLIENT, APPLICATION, COUNTRY

_LOGGER = logging.getLogger(__name__)

class BringAPI:
    """Async Bring! API Client."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str, list_name: str, cache_dir: str):
        self.session = session
        self.email = email
        self.password = password
        self.list_name = list_name
        self.cache_dir = cache_dir
        
        self.auth_data: Dict[str, Any] = {}
        self.list_uuid: Optional[str] = None
        self.catalog_cache: List[str] = []
        
        self._cache_file = os.path.join(self.cache_dir, "bring_auth_cache.json")
        self._catalog_file = os.path.join(self.cache_dir, "bring_catalog_cache.json")

    def _get_headers(self) -> Dict[str, str]:
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

    async def get_catalog(self) -> List[str]:
        """Fetch the list catalog (known items)."""
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

        list_uuid = await self.get_list_uuid()
        if not list_uuid:
            return []

        try:
            url = f"{API_BASE}/v2/bringlists/{list_uuid}/details"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    self.catalog_cache = [i.get('itemId') for i in items if i.get('itemId')]
                    def _save():
                        os.makedirs(os.path.dirname(self._catalog_file), exist_ok=True)
                        with open(self._catalog_file, 'w', encoding='utf-8') as f:
                            json.dump(self.catalog_cache, f, ensure_ascii=False)
                    await asyncio.to_thread(_save)
                    return self.catalog_cache
        except Exception as e:
            _LOGGER.error("Error fetching catalog: %s", str(e))
        return []

    async def get_active_items(self) -> List[Dict[str, str]]:
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

    async def execute_batch_changes(self, changes: List[Dict[str, Any]]) -> bool:
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
