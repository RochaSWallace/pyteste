from fake_useragent import UserAgent
from core.download.application.use_cases import DownloadUseCase
from core.providers.infra.template.wordpress_madara import WordPressMadara
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin
import re

class GalinhaSamuraiProvider(WordPressMadara):
    name = 'Galinha Samurai'
    lang = 'pt-Br'
    domain = ['galinhasamurai.com']

    def __init__(self):
        self.url = 'https://galinhasamurai.com'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div#section_cap a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div#Imagens img'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = None
        ua = UserAgent()
        user = ua.chrome
        self.headers = {'host': 'galinhasamurai.com', 'user_agent': user, 'referer': f'{self.url}/series'}
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        return Manga(id=link, name=title)

    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        
        # Busca capítulos diretamente do HTML
        data = soup.select(self.query_chapters)

        chs = []
        for el in data:
            ch_id = self.get_root_relative_or_absolute_link(el, uri)
            ch_number = el.text.strip()
            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs
    
    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Busca imagens diretamente da div#Imagens
        data = soup.select(self.query_pages)
        
        list = [] 
        for el in data:
            img_src = el.get('src')
            if img_src:
                list.append(img_src)

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, list)
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        if headers is not None:
            headers = headers | self.headers
        else:
            headers = self.headers
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)