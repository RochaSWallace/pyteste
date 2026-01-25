from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
import time
from core.download.application.use_cases import DownloadUseCase
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages
from urllib.parse import urljoin

class YuriLiveProvider(WordPressMadara):
    name = 'Yuri live'
    lang = 'pt-Br'
    domain = ['yuri.live']

    def __init__(self):
        self.url = 'https://yuri.live/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
    
    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        uri = self._add_query_params(uri, {'style': 'list'})
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
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        # Headers que correspondem à requisição real do navegador
        flickr_headers = {
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'Referer': 'https://yuri.live/'
        }
        
        if headers:
            flickr_headers.update(headers)
        
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=flickr_headers, cookies=cookies, timeout=10)