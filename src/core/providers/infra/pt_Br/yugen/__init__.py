from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from urllib.parse import urljoin
import re
import json

class YugenProvider(WordpressEtoshoreMangaTheme):
    name = 'Yugen mangas'
    lang = 'pt-Br'
    domain = ['yugenmangasbr.yocat.xyz']

    def __init__(self) -> None:
        self.url = 'https://yugenmangasbr.yocat.xyz'
        self.link = 'https://yugenmangasbr.yocat.xyz'
        self.cdn = 'https://api.yugenweb.com/media/'
        self.api = 'https://api.yugenweb.com/'
        
        self.get_title = 'h1'
        self.get_chapters_list = 'div.grid.gap-2'
        self.chapter = 'a[href^="/reader/"]'
        self.get_chapter_number = 'p.font-semibold'
        self.get_div_page = 'div#readerarea'
        self.get_pages = 'img'
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)
        return Manga(link, title.get_text().strip().replace('\n', ' '))

    def getChapters(self, id: str) -> List[Chapter]:
        all_chapters = []
        page = 1
        title = None
        
        while True:
            # Monta a URL com o parâmetro de página
            if '?' in id:
                url = f"{id}&page={page}"
            else:
                url = f"{id}?page={page}"
            
            response = Http.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Pega o título apenas na primeira página
            if page == 1:
                title_element = soup.select_one(self.get_title)
                if title_element:
                    title = title_element.get_text().strip().replace('\n', ' ')
            
            # Busca a lista de capítulos
            chapters_list = soup.select_one(self.get_chapters_list)
            
            # Se não encontrou a lista de capítulos, sai do loop
            if not chapters_list:
                break
            
            # Busca os capítulos dentro da lista
            chapters = chapters_list.select(self.chapter)
            
            # Se não encontrou capítulos, sai do loop
            if not chapters:
                break
            
            # Adiciona os capítulos encontrados à lista
            for ch in chapters:
                number_element = ch.select_one(self.get_chapter_number)
                if number_element:
                    link = urljoin(self.url, ch.get('href'))
                    all_chapters.append(Chapter(link, number_element.get_text().strip(), title))
            
            # Incrementa a página para a próxima iteração
            page += 1
        
        return all_chapters
    
    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Encontra todos os scripts na página
        scripts = soup.find_all('script')
        if scripts:
            last_script = scripts[-1]

        script_content = last_script.string
        pages_data = []
        # Procura pelo padrão "pages":[{...}] dentro do JSON escapado
        # O padrão está em: self.__next_f.push([1,"18:...\"pages\":[{...}]..."])
        match = re.search(r'\\"pages\\":\[(\{[^\]]+\}(?:,\{[^\]]+\})*)\]', script_content)
        if match:
            try:
                # Remove as barras de escape e reconstrói o array JSON
                json_str = '[' + match.group(1).replace('\\"', '"') + ']'
                pages_json = json.loads(json_str)
                pages_data = pages_json
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")

        
        # Ordena as páginas pelo número
        if pages_data:
            pages_data.sort(key=lambda x: x.get('number', 0))
        
        # Monta as URLs completas
        links = []
        for page in pages_data:
            path = page.get('path', '')
            if path:
                # URL completa: https://api.yugenweb.com/media/ + path
                links.append(urljoin(self.cdn, path))
        
        return Pages(ch.id, ch.number, ch.name, links)