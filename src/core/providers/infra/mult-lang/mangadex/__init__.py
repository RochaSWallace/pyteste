from typing import List
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.application.use_cases import DownloadUseCase

class MangaDexProvider(Base):
    name = 'MangaDex'
    lang = 'mult-lang'
    domain = ['mangadex.org']

    def __init__(self) -> None:
        self.Api = 'https://api.mangadex.org'
        self.CDN = 'https://cmdxd98sb0x3yprd.mangadex.network/data'

    def _extract_manga_id(self, value: str) -> str:
        parts = value.strip('/').split('/')
        if 'title' in parts:
            idx = parts.index('title')
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return parts[-1]
    
    def getManga(self, link: str) -> Manga:
        manga_id = self._extract_manga_id(link)
        headers = {
            'accept': '*/*',
            'accept-language': 'pt-BR,pt;q=0.5',
            'referer': 'https://mangadex.org/'
        }
        response = Http.get(
            f'{self.Api}/manga/{manga_id}?includes[]=artist&includes[]=author&includes[]=cover_art',
            headers=headers
        ).json()
        titles = response['data']['attributes']['title']
        title = (
            titles.get('pt-br')
            or titles.get('en')
            or titles.get('ja-ro')
            or next(iter(titles.values()), 'Sem titulo')
        )
        return Manga(link, title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        manga_id = self._extract_manga_id(id)
        headers = {
            'accept': '*/*',
            'accept-language': 'pt-BR,pt;q=0.5',
            'referer': 'https://mangadex.org/'
        }

        manga_response = Http.get(
            f'{self.Api}/manga/{manga_id}?includes[]=artist&includes[]=author&includes[]=cover_art',
            headers=headers
        ).json()

        titles = manga_response['data']['attributes']['title']
        title = (
            titles.get('pt-br')
            or titles.get('en')
            or titles.get('ja-ro')
            or next(iter(titles.values()), 'Sem titulo')
        )

        limit = 96
        offset = 0
        seen_ids = set()
        chapters = []

        while True:
            feed_url = (
                f'{self.Api}/manga/{manga_id}/feed?'
                f'translatedLanguage[]=pt-br&limit={limit}&'
                'includes[]=scanlation_group&includes[]=user&'
                'order[volume]=desc&order[chapter]=desc&'
                f'offset={offset}&'
                'contentRating[]=safe&contentRating[]=suggestive&'
                'contentRating[]=erotica&contentRating[]=pornographic&'
                'includeUnavailable=0&excludeExternalUrl=blinktoon.com'
            )

            feed_response = Http.get(feed_url, headers=headers).json()
            page_data = feed_response.get('data', [])

            if not page_data:
                break

            for ch in page_data:
                chapter_id = ch.get('id')
                if not chapter_id or chapter_id in seen_ids:
                    continue
                seen_ids.add(chapter_id)

                chapter_number = ch.get('attributes', {}).get('chapter')
                chapter_label = f'Capítulo {chapter_number}' if chapter_number else 'Capítulo sem número'
                chapters.append(Chapter(chapter_id, chapter_label, title))

            if len(page_data) < limit:
                break

            offset += limit

        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        try:
            response = Http.get(f'{self.Api}/at-home/server/{ch.id}?forcePort443=false').json()
            hash_code = response['chapter']['hash']
            list = []
            for pgs in response['chapter']['data']:
                list.append(f'{self.CDN}/{hash_code}/{pgs}')
            return Pages(ch.id, ch.number, ch.name, list)
        except Exception as e:
            print(e)

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        fetch_headers = {
            'referer': 'https://mangadex.org/',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Brave";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"'
        }

        if headers is not None:
            headers = headers | fetch_headers
        else:
            headers = fetch_headers

        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)

