from typing import List
from urllib.parse import parse_qs, urlparse

from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Manga, Pages
from core.providers.infra.template.base import Base


class OneReaderProvider(Base):
    name = 'OneReader'
    lang = 'pt_Br'
    domain = ['onereader.net']

    def __init__(self) -> None:
        self.api = 'https://api.onereader.net/api'

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
        pages = [page for page in pages if isinstance(page, str) and page]

        return Pages(ch.id, ch.number, ch.name, pages)
