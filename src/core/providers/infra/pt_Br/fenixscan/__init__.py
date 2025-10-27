from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs

class FenixScansProvider(WordPressMadara):
    name = 'Fenix Scans'
    lang = 'pt_Br'
    domain = ['fenixscan.xyz']

    def __init__(self):
        self.url = 'https://fenixscan.xyz/'

        self.path = ''

        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div.chapters-grid'
        self.query_chapter = 'div.chapter-item'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.image-wrapper'
        self.query_title_for_uri = 'h1.obra-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
    
    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        chapters = soup.select(self.query_chapter)
        chs = []
        for el in chapters:
            ch_id = el.find('a').get('href')
            ch_number = el.get('data-num').strip()
            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs
