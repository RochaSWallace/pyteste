from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs
import nodriver as uc
from time import sleep

class MangaLivreProvider(WordPressMadara):
    name = 'Manga Livre'
    lang = 'pt_Br'
    domain = ['mangalivre.tv']

    def __init__(self):
        self.url = 'https://mangalivre.tv/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
    
    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        uri = self._add_query_params(uri, {'style': 'list'})
        
        # Primeira tentativa: HTTP normal
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_pages)
        if not data:
            uri = self._remove_query_params(uri, ['style'])
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            soup = BeautifulSoup(response.content, 'html.parser')
            data = soup.select(self.query_pages)
        
        # Verifica se encontrou imagens
        pages_list = [] 
        for el in data:
            pages_list.append(self._process_page_element(el, uri))
        
        # Se não encontrou imagens, usa nodriver para bypass do bloqueio
        if not pages_list:
            print("[MangaLivre] Nenhuma imagem encontrada com HTTP, usando nodriver...")
            content = self._get_page_with_nodriver(uri)
            if content:
                soup = BeautifulSoup(content, 'html.parser')
                data = soup.select(self.query_pages)
                for el in data:
                    pages_list.append(self._process_page_element(el, uri))

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, pages_list)
    
    def _get_page_with_nodriver(self, url: str) -> str:
        """Usa nodriver em modo headless para burlar bloqueios"""
        content = None
        async def get_page():
            nonlocal content
            browser = await uc.start()
            page = await browser.get(url)
            sleep(10)
            
            # Aguarda até que "por favor" suma da página (indica carregamento completo)
            max_attempts = 30  # máximo 30 tentativas (30 segundos)
            for _ in range(max_attempts):
                page_content = await page.get_content()
                if "por favor" not in page_content.lower():
                    content = page_content
                    break
                sleep(1)
            else:
                # Se timeout, retorna o que tiver
                content = await page.get_content()
            
            browser.stop()
        uc.loop().run_until_complete(get_page())
        return content
    
    def _process_page_element(self, element, referer):
        element = element.find('img') or element.find('image')
        src = element.get('data-url') or element.get('data-src') or element.get('srcset') or element.get('src')
        element['src'] = src
        if 'data:image' in src:
            return src.split()[0]
        else:
            uri = urlparse(self.get_absolute_path(element, referer))
            canonical = parse_qs(uri.query).get('src')
            if canonical and canonical[0].startswith('http'):
                uri = uri._replace(query='')
                uri = uri._replace(path=canonical[0])
            return self.create_connector_uri({'url': uri.geturl(), 'referer': referer})

    def _add_query_params(self, url, params):
        url_parts = list(urlparse(url))
        query = dict(parse_qs(url_parts[4]))
        query.update(params)
        url_parts[4] = urlencode(query, doseq=True)
        return urlunparse(url_parts)

    def _remove_query_params(self, url, params):
        url_parts = list(urlparse(url))
        query = dict(parse_qs(url_parts[4]))
        for param in params:
            query.pop(param, None)
        url_parts[4] = urlencode(query, doseq=True)
        return urlunparse(url_parts)