from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlparse, parse_qs
import re

class KairostoonsProvider(WordpressEtoshoreMangaTheme):
    name = 'Kairo Toons'
    lang = 'pt_Br'
    domain = ['kairostoons.net']

    def __init__(self) -> None:
        self.base_url = 'https://kairostoons.net'
        self.get_title = 'h1.manga-title'
        self.get_chapters_list = 'ul.chapter-item-list'
        self.chapter = 'li.chapter-item > a.chapter-link'
        self.get_chapter_number = 'span.chapter-number'
        self.get_pages = 'canvas.chapter-image-canvas'
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one('h1.manga-title')
        if not title:
            raise ValueError("Título do manga não encontrado")
        return Manga(link, title.get_text().strip())

    def getChapters(self, id: str) -> List[Chapter]:
        """
        Obtém todos os capítulos, iterando por todas as páginas se necessário
        """
        all_chapters = []
        page = 1
        manga_title = None
        
        while True:
            # Monta URL com paginação
            if page == 1:
                url = id
            else:
                url = f"{id}?page={page}"
            
            response = Http.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Pega o título do manga (apenas na primeira vez)
            if not manga_title:
                title_elem = soup.select_one('h1.manga-title')
                if title_elem:
                    manga_title = title_elem.get_text().strip()
                else:
                    manga_title = "Desconhecido"
            
            # Encontra a lista de capítulos
            chapter_items = soup.select('ul.chapter-item-list > li.chapter-item > a.chapter-link')
            
            # Se não encontrou capítulos, para o loop
            if not chapter_items:
                break
            
            # Adiciona os capítulos encontrados
            for ch in chapter_items:
                chapter_url = ch.get('href')
                if chapter_url:
                    # Monta URL completa se for relativa
                    chapter_url = urljoin(self.base_url, chapter_url)
                    
                    # Extrai o número do capítulo
                    number_elem = ch.select_one('span.chapter-number')
                    if number_elem:
                        chapter_number = number_elem.get_text().strip()
                    else:
                        chapter_number = "Capítulo"
                    
                    all_chapters.append(Chapter(chapter_url, chapter_number, manga_title))
            
            # Verifica se há próxima página
            # Procura por link de próxima página (›)
            next_page = soup.select_one('nav ul.pagination li.page-item:not(.disabled) a.page-link[aria-label="Próximo"]')
            if not next_page:
                # Alternativa: procura por qualquer link "›" não desabilitado
                next_links = soup.select('nav ul.pagination li.page-item:not(.disabled) a.page-link')
                has_next = any('›' in link.get_text() for link in next_links)
                if not has_next:
                    break
            
            page += 1
        
        return all_chapters

    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Encontra todos os elementos canvas com as imagens
        canvas_elements = soup.select('canvas.chapter-image-canvas')
        
        image_list = []
        for canvas in canvas_elements:
            data_src = canvas.get('data-src-url')
            if data_src:
                # Monta URL completa
                full_url = urljoin(self.base_url, data_src)
                image_list.append(full_url)
        
        return Pages(ch.id, ch.number, ch.name, image_list)
