from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs

class PandaSukiProvider(WordPressMadara):
    name = 'PandaSuki'
    lang = 'pt_Br'
    domain = ['pandasuki.net', 'www.pandasuki.net']

    def __init__(self):
        self.url = 'https://pandasuki.net'
        self.path = ''

        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div.lista-capitulos-container > a'
        self.query_chapters_title_bloat = None
        self.query_pages = '#paginas figure.gallery-item, div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.elementor-heading-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'


    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        dom = soup.select('body')[0]
        data = dom.select(self.query_chapters)
        placeholder = dom.select_one(self.query_placeholder)
        if placeholder:
            try:
                data = self._get_chapters_ajax(id)
            except Exception:
                try:
                    data = self._get_chapters_ajax_old(placeholder['data-id'])
                except Exception:
                    pass

        chs = []
        for el in data:
            ch_id = self.get_root_relative_or_absolute_link(el, uri)
            raw_text = ' '.join(el.get_text(' ', strip=True).split())

            # Remove datas no formato 11/01/2026 quando vierem junto do título.
            raw_without_date = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '', raw_text).strip()
            number_match = re.search(r'\d+(?:\.\d+)?', raw_without_date)
            ch_number = number_match.group(0) if number_match else raw_without_date

            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs