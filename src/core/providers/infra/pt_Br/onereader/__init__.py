from typing import List
from urllib.parse import parse_qs, urljoin, urlparse

from core.__seedwork.infra.http import Http
from core.download.application.use_cases import DownloadUseCase
from core.providers.domain.entities import Chapter, Manga, Pages
from core.providers.infra.template.base import Base


class OneReaderProvider(Base):
    name = 'OneReader'
    lang = 'pt_Br'
    domain = ['onereader.net']

    def __init__(self) -> None:
        self.api_root = 'https://api.onereader.net'
        self.api = 'https://api.onereader.net/api'
        self.download_headers = {
            'accept': '*/*',
            'accept-language': 'pt-BR,pt;q=0.5',
            'origin': 'https://onereader.net',
            'referer': 'https://onereader.net/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/146.0.0.0 Safari/537.36'
            ),
        }

    def _extract_manga_key(self, value: str) -> str:
        parsed = urlparse(value)
        query_id = parse_qs(parsed.query).get('id', [None])[0]
        if query_id:
            return query_id

        path = parsed.path.strip('/')
        if path:
            return path.split('/')[-1]

        return value.strip()

    def _get_manga_data(self, manga_key: str) -> dict:
        return Http.get(f'{self.api}/mangas/{manga_key}').json()

    def _build_page_url(self, page: str) -> str:
        # Alguns capítulos retornam caminhos protegidos relativos (/api/images/protected/...)
        if page.startswith('http://') or page.startswith('https://'):
            return page
        return urljoin(self.api_root, page)

    @staticmethod
    def _chapter_sort_key(chapter_number: str):
        try:
            return float(chapter_number)
        except (TypeError, ValueError):
            return float('inf')

    def getManga(self, link: str) -> Manga:
        manga_key = self._extract_manga_key(link)
        manga_data = self._get_manga_data(manga_key)
        manga_name = manga_data.get('display_name') or manga_data.get('name') or manga_key
        return Manga(manga_key, manga_name)

    def getChapters(self, manga_id: str) -> List[Chapter]:
        manga_key = self._extract_manga_key(manga_id)
        manga_data = self._get_manga_data(manga_key)
        manga_name = manga_data.get('display_name') or manga_data.get('name') or manga_key

        chapters_data = Http.get(f'{self.api}/chapters/{manga_key}').json()
        chapters_list = []

        if isinstance(chapters_data, dict):
            ordered_chapters = sorted(
                chapters_data.values(),
                key=lambda chapter: self._chapter_sort_key(chapter.get('chapter_number')),
            )

            for chapter in ordered_chapters:
                chapter_number = str(chapter.get('chapter_number', '')).strip()
                if not chapter_number:
                    continue

                chapter_api_url = f'{self.api}/chapters/{manga_key}/{chapter_number}'
                chapters_list.append(Chapter(chapter_api_url, chapter_number, manga_name))

        return chapters_list

    def getPages(self, ch: Chapter) -> Pages:
        chapter_data = Http.get(ch.id).json()
        pages = chapter_data.get('pages', []) if isinstance(chapter_data, dict) else []
        pages = [self._build_page_url(page) for page in pages if isinstance(page, str) and page]

        return Pages(ch.id, ch.number, ch.name, pages)

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        if headers is not None:
            headers = headers | self.download_headers
        else:
            headers = self.download_headers

        return DownloadUseCase().execute(
            pages=pages,
            fn=fn,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )
