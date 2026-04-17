from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import requests
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga


class ImperiodabritanniaProvider(Base):
    name = 'Imperio da britannia'
    lang = 'pt_Br'
    domain = ['imperiodabritannia.net', 'imperiodabritannia.com']

    SECRET = 'mangotoons_encryption_key_2025'
    SALT = 'salt'

    def __init__(self):
        self.url = 'https://imperiodabritannia.net'
        self.base_api = f'{self.url}/api'
        self.session = requests.Session()
        self._slug_cache_by_id: Dict[int, str] = {}

    # ----------------------------
    # Criptografia API
    # ----------------------------
    def _derive_key(self) -> bytes:
        digest = hashes.Hash(hashes.SHA256())
        digest.update((self.SECRET + self.SALT).encode('utf-8'))
        return digest.finalize()

    def _decrypt_payload(self, encrypted_text: str, key: bytes) -> Any:
        parts = encrypted_text.split(':')
        if len(parts) != 2:
            return json.loads(encrypted_text)

        iv = bytes.fromhex(parts[0])
        ciphertext = bytes.fromhex(parts[1])

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()

        return json.loads(plaintext.decode('utf-8'))

    def _encrypt_payload(self, obj: Any, key: bytes) -> str:
        # Gera IV aleatorio por requisicao para manter compatibilidade com o cliente web.
        iv = os.urandom(16)

        plaintext = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()

        return f'{iv.hex()}:{ciphertext.hex()}'

    def _api_fetch(
        self,
        path: str,
        method: str = 'GET',
        body: Any | None = None,
        encrypt_body: bool = True,
        decrypt_response: bool = True,
    ) -> Any:
        key = self._derive_key()
        url = f'{self.url.rstrip("/")}{path}'

        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Referer': f'{self.url.rstrip("/")}/',
        }

        request_body: Optional[str] = None
        if body is not None:
            if encrypt_body:
                request_body = self._encrypt_payload(body, key)
                headers['X-Encrypted'] = 'true'
            else:
                request_body = json.dumps(body, ensure_ascii=False)

        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            data=request_body,
            timeout=30,
        )
        response.raise_for_status()

        encrypted_header = response.headers.get('X-Encrypted')
        if decrypt_response and encrypted_header == 'true':
            return self._decrypt_payload(response.text, key)

        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            return response.json()

        try:
            return response.json()
        except ValueError:
            return response.text

    # ----------------------------
    # Helpers de parsing
    # ----------------------------
    def _parse_slug_from_link(self, link_or_slug: str) -> str:
        if not link_or_slug:
            raise ValueError('Link/slug vazio')

        if re.match(r'^https?://', link_or_slug):
            match = re.search(r'/obra/([^/?#]+)', link_or_slug)
            if match:
                return match.group(1)
            return link_or_slug.rstrip('/').split('/')[-1]

        cleaned = link_or_slug.strip('/')
        if '/obra/' in cleaned:
            return cleaned.split('/obra/')[-1].split('/')[0]
        return cleaned.split('/')[-1]

    def _to_seconds_from_iso(self, value: str) -> int:
        if not value:
            return 86400
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            now = datetime.now(ZoneInfo('UTC'))
            delta = int((now - dt.astimezone(ZoneInfo('UTC'))).total_seconds())
            return delta if delta >= 0 else 3600
        except Exception:
            return 86400

    def _chapter_api_number(self, numero: str) -> str:
        if numero is None:
            return '0'

        text = str(numero).strip()
        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
            return text
        except Exception:
            return text

    def _encode_chapter_id(self, obra_id: int, chapter_ref: str, slug: str) -> str:
        return f'{obra_id}|{chapter_ref}|{slug}'

    def _decode_chapter_id(self, chapter_id: str) -> Tuple[int, str, str]:
        parts = str(chapter_id).split('|', 2)
        if len(parts) != 3:
            raise ValueError(f'Formato de chapter id invalido: {chapter_id}')
        return int(parts[0]), parts[1], parts[2]

    def _slugify(self, text: str) -> str:
        if not text:
            return ''
        slug = text.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')

    def _get_slug_by_obra_id(self, obra_id: int) -> str:
        if obra_id in self._slug_cache_by_id:
            return self._slug_cache_by_id[obra_id]

        try:
            data = self._api_fetch(f'/api/obras/{obra_id}')
            obra = data.get('obra', {}) if isinstance(data, dict) else {}
            slug = str(obra.get('slug', '')).strip()
            if slug:
                self._slug_cache_by_id[obra_id] = slug
                return slug
        except Exception:
            pass

        return ''


    def getManga(self, link: str) -> Manga:
        slug = self._parse_slug_from_link(link)
        data = self._api_fetch(f'/api/obras/by-slug/{slug}')

        obra = data.get('obra', {}) if isinstance(data, dict) else {}
        titulo = obra.get('nome') or slug.replace('-', ' ').title()

        return Manga(link, titulo)

    def getChapters(self, id: str) -> List[Chapter]:
        slug = self._parse_slug_from_link(id)
        data = self._api_fetch(f'/api/obras/by-slug/{slug}')

        obra = data.get('obra', {}) if isinstance(data, dict) else {}
        obra_id = obra.get('id')
        nome_obra = obra.get('nome') or slug.replace('-', ' ').title()
        capitulos = obra.get('capitulos', [])

        if not obra_id:
            return []

        chs: List[Chapter] = []
        for cap in capitulos:
            numero = str(cap.get('numero', '')).strip()
            chapter_ref = self._chapter_api_number(numero)
            ch_id = self._encode_chapter_id(obra_id, chapter_ref, slug)
            chs.append(Chapter(ch_id, chapter_ref, nome_obra))

        # API geralmente retorna crescente, garantimos ordenação por número.
        def chapter_sort_key(ch: Chapter):
            try:
                return float(ch.number)
            except Exception:
                return 0.0

        chs.sort(key=chapter_sort_key)
        return chs

    def getPages(self, ch: Chapter) -> Pages:
        obra_id, chapter_ref, slug = self._decode_chapter_id(ch.id)
        data = self._api_fetch(f'/api/obras/{obra_id}/capitulos/{chapter_ref}')

        capitulo = data.get('capitulo', {}) if isinstance(data, dict) else {}
        paginas = capitulo.get('paginas', [])

        urls: List[str] = []
        for page in paginas:
            cdn_id = page.get('cdn_id')
            if isinstance(cdn_id, str) and cdn_id.startswith('http'):
                urls.append(cdn_id)

        chapter_name = ch.name or f'{slug} - {chapter_ref}'
        return Pages(ch.id, ch.number, chapter_name, urls)
