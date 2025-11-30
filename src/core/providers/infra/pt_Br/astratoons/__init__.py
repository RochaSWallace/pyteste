from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

class AstraToonsProvider(WordpressEtoshoreMangaTheme):
    name = 'Astra Toons'
    lang = 'pt_Br'
    domain = ['new.astratoons.com']

    def __init__(self):
        self.url = 'https://new.astratoons.com'
        self.link = 'https://new.astratoons.com/'
        self.get_title = 'h1'
        self.get_chapters_list = '#chapter-list'
        self.chapter = 'a[href*="/capitulo/"]'
        self.get_chapter_name = 'span.text-lg'
        self.get_div_page = '#reader-container'
        self.get_pages = 'img[src]'

    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_element = soup.select_one(self.get_title)
        title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
            
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        list = []
        
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar título do mangá usando self.get_title
        title_element = soup.select_one(self.get_title)
        manga_title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
        
        # Buscar container de capítulos usando self.get_chapters_list
        chapters_container = soup.select_one(self.get_chapters_list)
        
        if not chapters_container:
            print(f"[AstraToons] Container {self.get_chapters_list} não encontrado")
            return list
        
        # Buscar todos os links de capítulos usando self.chapter
        chapter_links = chapters_container.select(self.chapter)
        
        print(f"[AstraToons] Encontrados {len(chapter_links)} capítulos")
        
        for ch_link in chapter_links:
            chapter_url = ch_link.get('href')
            
            if not chapter_url:
                continue
            
            # Extrair nome do capítulo usando self.get_chapter_name
            chapter_text_elem = ch_link.select_one(self.get_chapter_name)
            
            if chapter_text_elem:
                chapter_name = chapter_text_elem.get_text().strip()
            else:
                # Fallback: extrair do href
                chapter_num = chapter_url.split('/capitulo/')[-1]
                chapter_name = f"Capítulo {chapter_num}"
            
            chapter_obj = Chapter(
                chapter_url if chapter_url.startswith('http') else f"{self.url}{chapter_url}",
                chapter_name,
                manga_title
            )
            list.append(chapter_obj)
        
        return list

    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar container de imagens usando self.get_div_page
        images_container = soup.select_one(self.get_div_page)
        
        if not images_container:
            print(f"[AstraToons] Container {self.get_div_page} não encontrado")
            return Pages(ch.id, ch.number, ch.name, [])
        
        # Buscar todas as imagens usando self.get_pages
        image_elements = images_container.select(self.get_pages)
        
        if not image_elements:
            print(f"[AstraToons] Nenhuma imagem encontrada com seletor {self.get_pages}")
            return Pages(ch.id, ch.number, ch.name, [])
        
        list = []
        for img in image_elements:
            img_src = img.get('src')
            if img_src:
                # URLs já vêm completas (https://new.astratoons.com/proxy/image/...)
                list.append(img_src)
        
        print(f"[AstraToons] Encontradas {len(list)} páginas")
        return Pages(ch.id, ch.number, ch.name, list)