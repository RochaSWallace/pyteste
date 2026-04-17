import re
from typing import Dict, List

from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Manga, Pages
from core.providers.infra.template.base import Base


class VegitoonsBlackProvider(Base):
    name = 'Vegitoons Black'
    lang = 'pt_Br'
    domain = ['vegitoons.black', 'www.vegitoons.black']
    has_login = False

    def __init__(self) -> None:
        self.api = 'https://vegitoons.black/api'
        self.cdn = 'https://cdn.vegitoons.black'
        self.headers = {
            'accept': '*/*',
            'accept-language': 'pt-BR,pt;q=0.5',
            'content-type': 'application/json',
            'scan-id': '1',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'referer': 'https://vegitoons.black/',
            'user-agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/146.0.0.0 Safari/537.36'
            ),
        }

    def _extract_obra_id(self, value: str) -> str:
        text = str(value).strip()
        if text.isdigit():
            return text

        for pattern in (r'/obra/(\d+)', r'/obras/(\d+)'):
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        last_number = re.search(r'(\d+)(?:/)?$', text)
        if last_number:
            return last_number.group(1)

        raise ValueError(f'Nao foi possivel extrair o id da obra: {value}')

    @staticmethod
    def _chapter_sort_key(value: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float('inf')

    @staticmethod
    def _chapter_number(chapter_data: Dict) -> str:
        cap_numero = chapter_data.get('cap_numero')
        if cap_numero is not None and str(cap_numero).strip():
            return str(cap_numero)

        cap_nome = str(chapter_data.get('cap_nome') or '').strip()
        match = re.search(r'(\d+(?:\.\d+)?)', cap_nome)
        if match:
            return match.group(1)

        return cap_nome

    def _get_obra_data(self, obra_id: str) -> Dict:
        response = Http.get(f'{self.api}/obras/{obra_id}', headers=self.headers)
        return response.json()

    def _get_capitulo_data(self, capitulo_id: str) -> Dict:
        response = Http.get(f'{self.api}/capitulos/{capitulo_id}', headers=self.headers)
        return response.json()

    def getManga(self, link: str) -> Manga:
        obra_id = self._extract_obra_id(link)
        data = self._get_obra_data(obra_id)
        title = data.get('obr_nome') or f'Obra {obra_id}'
        return Manga(obra_id, title)

    def getChapters(self, manga_id: str) -> List[Chapter]:
        obra_id = self._extract_obra_id(manga_id)
        data = self._get_obra_data(obra_id)

        title = data.get('obr_nome') or f'Obra {obra_id}'
        chapters = []
        for chapter_data in data.get('capitulos', []):
            cap_id = chapter_data.get('cap_id')
            if cap_id is None:
                continue

            number = self._chapter_number(chapter_data)
            if not number:
                continue

            chapters.append(Chapter(str(cap_id), number, title))

        chapters.sort(key=lambda chapter: self._chapter_sort_key(chapter.number))
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        data = self._get_capitulo_data(str(ch.id))

        images = []
        for page in data.get('cap_paginas', []):
            if not isinstance(page, dict):
                continue

            path = str(page.get('path') or '').strip('/')
            src = str(page.get('src') or '').strip('/')

            if path.startswith('http://') or path.startswith('https://'):
                full_url = path
            elif path:
                full_url = f'{self.cdn}/{path}'
            elif src:
                obra_id = data.get('obr_id')
                cap_numero = data.get('cap_numero')
                if obra_id is None or cap_numero is None:
                    continue
                full_url = f'{self.cdn}/scans/1/obras/{obra_id}/capitulos/{cap_numero}/{src}'
            else:
                continue

            if full_url not in images:
                images.append(full_url)

        return Pages(ch.id, ch.number, ch.name, images)
