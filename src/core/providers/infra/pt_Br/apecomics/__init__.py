from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import re
import json

class ApeComicsProvider(WordpressEtoshoreMangaTheme):
    name = 'Ape Comics'
    lang = 'pt_Br'
    domain = ['apecomics.net']

    def __init__(self) -> None:
        self.url = 'https://apecomics.net'
        self.link = 'https://apecomics.net'
        self.get_title = 'h1'
        self.get_chapters_list = 'div.eplister#chapterlist > ul'
        self.chapter = 'li a'
        self.get_chapter_number = 'span.chapternum'
        self.get_div_page = 'div#readerarea'
        self.get_pages = 'img'
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)
        return Manga(link, title.get_text().strip())

    def getChapters(self, id: str) -> List[Chapter]:
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        chapters_list = soup.select_one(self.get_chapters_list)
        chapter = chapters_list.select(self.chapter)
        title = soup.select_one(self.get_title)
        list = []
        for ch in chapter:
            number = ch.select_one(self.get_chapter_number)
            list.append(Chapter(ch.get('href'), number.get_text().strip(), title.get_text().strip()))
        return list

    def getPages(self, ch: Chapter) -> Pages:
        try:
            response = Http.get(ch.id, timeout=getattr(self, 'timeout', None))
            
            # Decodifica o conteúdo
            html_content = response.content.decode('utf-8') if isinstance(response.content, bytes) else response.content
            
            # Método 1: Extrai imagens do script ts_reader.run()
            pattern = r'ts_reader\.run\((\{.*?\})\);'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                try:
                    json_str = match.group(1)
                    data = json.loads(json_str)
                    
                    # Extrai as imagens de todos os sources disponíveis
                    all_images = []
                    if 'sources' in data:
                        for source in data['sources']:
                            images = source.get('images', [])
                            for img in images:
                                if img not in all_images:
                                    all_images.append(img)
                    
                    if all_images:
                        print(f"[APECOMICS] ✓ {len(all_images)} imagens extraídas")
                        return Pages(ch.id, ch.number, ch.name, all_images)
                except json.JSONDecodeError:
                    pass

            # Método 2: Fallback - Busca por URLs de imagens no HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # Busca por padrões de URLs de imagens (jpg, jpeg, png, webp)
            image_patterns = [
                r'https?://[^\s"\'<>]+\.jpg',
                r'https?://[^\s"\'<>]+\.jpeg', 
                r'https?://[^\s"\'<>]+\.png',
                r'https?://[^\s"\'<>]+\.webp',
                r'https?://[^\s"\'<>]+\.avif'
            ]

            all_urls = []
            for pattern in image_patterns:
                urls = re.findall(pattern, html_content, re.IGNORECASE)
                all_urls.extend(urls)

            # Remove duplicatas e filtra apenas imagens de capítulos
            seen = set()
            unique_urls = []
            for url in all_urls:
                # Decodifica caracteres escapados
                url_decoded = url.replace('\\/', '/').replace('%20', ' ')

                # Filtra apenas URLs de capítulos e evita placeholders
                if (url_decoded not in seen and 
                    'manga_auto_capitulos' in url_decoded and
                    'readerarea.svg' not in url_decoded):
                    seen.add(url_decoded)
                    unique_urls.append(url_decoded)

            if unique_urls:
                print(f"[APECOMICS] ✓ {len(unique_urls)} imagens extraídas (fallback)")
                return Pages(ch.id, ch.number, ch.name, unique_urls)

            # Método 3: Último recurso - busca no div readerarea
            images_div = soup.select_one(self.get_div_page)

            if images_div:
                image_tags = images_div.select(self.get_pages)
                img_list = []

                for img in image_tags:
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and 'readerarea.svg' not in src:
                        img_list.append(src)

                if img_list:
                    print(f"[APECOMICS] ✓ {len(img_list)} imagens extraídas (div)")
                    return Pages(ch.id, ch.number, ch.name, img_list)

            print("[APECOMICS] ✗ Nenhuma imagem encontrada")
            return Pages(ch.id, ch.number, ch.name, [])

        except Exception as e:
            print(f"[APECOMICS] ✗ Erro: {e}")
            return Pages(ch.id, ch.number, ch.name, [])
