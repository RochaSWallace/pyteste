from typing import List
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Manga, Pages
from core.download.infra.novel import NovelDownloadRepository
from core.providers.infra.template.wordpress_madara import WordPressMadara


class CentralNovelProvider(WordPressMadara):
    name = 'Central Novel'
    lang = 'pt-Br'
    domain = ['centralnovel.com']

    def __init__(self):
        super().__init__()
        self.url = 'https://centralnovel.com'
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div.bixbox.bxcl.epcheck li'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.entry-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'

    def getChapters(self, id: str) -> List[Chapter]:
        """Obtém lista de capítulos com estrutura personalizada do Central Novel"""
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Obtém o título do novel
        title_element = soup.select_one(self.query_title_for_uri)
        if not title_element:
            title_element = soup.select_one('head meta[property="og:title"]')
            title = title_element['content'].strip() if title_element and 'content' in title_element.attrs else 'Unknown'
        else:
            title = title_element.text.strip()
        
        # Busca o bloco principal de capítulos
        main_block = soup.select_one('div.bixbox.bxcl.epcheck')
        if not main_block:
            return []
        
        chapters = []
        
        # Busca todos os li dentro dos blocos colapsáveis
        chapter_items = main_block.select('li[data-id]')
        
        for index, item in enumerate(chapter_items[::-1], start=1):
            # Pega o link do capítulo
            link_element = item.select_one('a')
            if not link_element:
                continue
            
            ch_link = link_element.get('href', '')
            
            # Pega o número do capítulo (div.epl-num)
            num_element = item.select_one('div.epl-num')
            ch_number = num_element.text.strip() if num_element else ''
            ch_number = f"{index} - {ch_number}"
            
            # Pega o título do capítulo (div.epl-title)
            title_element = item.select_one('div.epl-title')
            
            if ch_link:
                chapters.append(Chapter(
                    id=ch_link,
                    number=ch_number,
                    name=title
                ))
        
        # Inverte para ordem crescente (geralmente vem do mais recente ao mais antigo)
        chapters.reverse()
        
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        """
        Para novels, retorna a URL do capítulo para ser processada pelo NovelDownloadRepository
        
        Args:
            ch: Objeto Chapter com id (URL) e informações do capítulo
        
        Returns:
            Pages: Objeto contendo a URL do capítulo para download
        """
        # Para novels, pages contém apenas a URL do capítulo
        # O download será feito pelo NovelDownloadRepository
        chapter_url = urljoin(self.url, ch.id)
        
        return Pages(
            id=ch.id,
            number=ch.number,
            name=ch.name,
            pages=[chapter_url]  # Lista com apenas a URL do capítulo
        )
    
    def download(self, pages: Pages, fn=None, headers=None, cookies=None):
        """
        Método de download customizado para novels usando NovelDownloadRepository
        
        Args:
            pages: Objeto Pages contendo URL do capítulo
            fn: Função de callback para progresso
            headers: Headers HTTP
            cookies: Cookies HTTP
        
        Returns:
            Chapter: Objeto contendo arquivos baixados
        """
        novel_downloader = NovelDownloadRepository()
        return novel_downloader.download(pages, fn, headers, cookies)

