from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

class AstraToonsProvider(WordpressEtoshoreMangaTheme):
    name = 'Astra Toons'
    lang = 'pt_Br'
    domain = ['astratoons.com']

    def __init__(self):
        self.url = 'https://astratoons.com'
        self.link = 'https://astratoons.com/'

        self.get_title = 'h1.manga-title'
        self.get_chapters_list = 'ul.chapter-item-list'
        self.chapter = 'li.chapter-item a.chapter-link'
        self.get_chapter_number = 'span.chapter-number'
        self.get_div_page = 'div.chapter-images-container'
        self.get_pages = 'img.chapter-image'

    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)
        return Manga(link, title.get_text().strip())

    def getChapters(self, id: str) -> List[Chapter]:
        list = []
        
        seen_chapter_urls = set()
        page_number = 1
        
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        title_element = soup.select_one(self.get_title)
        manga_title = title_element.get_text().strip() if title_element else "Título não encontrado"

        while True:
            paginated_url = f"{id}?page={page_number}"
            print(f"Buscando capítulos em: {paginated_url}")

            response = Http.get(paginated_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            chapters_container = soup.select_one(self.get_chapters_list)
            
            if not chapters_container:
                break
                
            chapters_on_page = chapters_container.select(self.chapter)

            if not chapters_on_page:
                break

            new_chapters_found_on_page = False

            for ch in chapters_on_page:
                chapter_url = ch.get('href')
                
                if chapter_url in seen_chapter_urls:
                    continue

                new_chapters_found_on_page = True
                seen_chapter_urls.add(chapter_url)

                number = ch.select_one(self.get_chapter_number)
                chapter_obj = Chapter(
                    f"{self.url}{chapter_url}",
                    number.get_text().strip(),
                    manga_title
                )
                list.append(chapter_obj)
            
            if not new_chapters_found_on_page:
                print("Página com capítulos repetidos encontrada. Finalizando a busca.")
                break
            
            page_number += 1

        return list

    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        images_container = soup.select_one('div.chapter-images-container, div#chapterImagesContainer')
        
        if images_container:
            images = soup.select_one(self.get_div_page)
            if images:
                image = images.select(self.get_pages)
                list = []
                for img in image:
                    list.append(f"{self.url}{img.get('src')}")
                return Pages(ch.id, ch.number, ch.name, list)
            else:
                raise Exception("Container de imagens não encontrado")

        # Busca pelos elementos canvas com data-src-url
        canvas_elements = images_container.select('canvas.chapter-image-canvas[data-src-url]')
        
        if not canvas_elements:
            # Fallback: tenta buscar qualquer canvas com data-src-url
            canvas_elements = soup.select('canvas[data-src-url]')
        
        list = []
        for canvas in canvas_elements:
            data_src_url = canvas.get('data-src-url')
            if data_src_url:
                # Se a URL começar com '/', adiciona o domínio base
                if data_src_url.startswith('/'):
                    full_url = f"{self.url.rstrip('/')}{data_src_url}"
                else:
                    full_url = data_src_url
                list.append(full_url)
        
        if not list:
            raise Exception("Nenhuma imagem encontrada nos elementos canvas")
            
        return Pages(ch.id, ch.number, ch.name, list)