from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs

class HiperCoolProvider(WordPressMadara):
    name = 'Hiper Cool'
    lang = 'pt_Br'
    domain = ['hiper.cool']

    def __init__(self):
        self.url = 'https://hiper.cool/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        
    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        # uri = self._add_query_params(uri, {'style': 'list'})
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_pages)
        if not data:
            uri = self._remove_query_params(uri, ['style'])
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            soup = BeautifulSoup(response.content, 'html.parser')
            data = soup.select(self.query_pages)
        list = [] 
        for el in data:
            list.append(self._process_page_element(el, uri))

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, list)
    