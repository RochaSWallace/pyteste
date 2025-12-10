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

class TaimuProvider(WordpressEtoshoreMangaTheme):
    name = 'Taimu mangas'
    lang = 'pt-Br'
    domain = ['taimumangas.rzword.xyz']

    def __init__(self) -> None:
        self.url = 'https://taimumangas.rzword.xyz'
        self.link = 'https://taimumangas.rzword.xyz'
        self.cdn = 'https://api.taimumangas.com/media/'
        self.api = 'https://api.taimumangas.com/'
        
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
        try:
            response = Http.get(ch.id)
            html_content = response.content.decode('utf-8') if isinstance(response.content, bytes) else response.content
            
            # Busca pelo padrão self.__next_f.push com chapterData
            pattern = r'self\.__next_f\.push\(\[1,"[^"]*chapterData[^"]*"\]\)'
            matches = re.findall(pattern, html_content)
            
            pages_data = []
            
            for match in matches:
                # Extrai o JSON dentro do push
                json_match = re.search(r'\[1,"(.*)"\]', match)
                if json_match:
                    json_str = json_match.group(1)
                    
                    # Procura especificamente pelo array "pages"
                    pages_pattern = r'\\"pages\\":\[(\{[^\]]+\}(?:,\{[^\]]+\})*)\]'
                    pages_match = re.search(pages_pattern, json_str)
                    
                    if pages_match:
                        try:
                            # Remove barras de escape e reconstrói o JSON
                            pages_json_str = '[' + pages_match.group(1).replace('\\"', '"') + ']'
                            pages_json = json.loads(pages_json_str)
                            
                            # Adiciona as páginas encontradas
                            for page in pages_json:
                                if page not in pages_data:
                                    pages_data.append(page)
                                    
                        except json.JSONDecodeError:
                            continue
            
            # Se não encontrou pelo método acima, tenta o método alternativo
            if not pages_data:
                soup = BeautifulSoup(html_content, 'html.parser')
                scripts = soup.find_all('script')
                
                for script in scripts:
                    if script.string and 'pages' in script.string:
                        script_content = script.string
                        
                        # Procura pelo padrão "pages":[{...}]
                        pages_pattern = r'\\"pages\\":\[(\{[^\]]+\}(?:,\{[^\]]+\})*)\]'
                        pages_match = re.search(pages_pattern, script_content)
                        
                        if pages_match:
                            try:
                                pages_json_str = '[' + pages_match.group(1).replace('\\"', '"') + ']'
                                pages_json = json.loads(pages_json_str)
                                pages_data = pages_json
                                break
                            except json.JSONDecodeError:
                                continue
            
            # Ordena as páginas pelo número
            if pages_data:
                pages_data.sort(key=lambda x: x.get('number', 0))
                
                # Monta as URLs completas
                links = []
                for page in pages_data:
                    path = page.get('path', '')
                    if path:
                        # URL completa: https://api.yugenweb.com/media/ + path
                        full_url = urljoin(self.cdn, path)
                        links.append(full_url)
                
                if links:
                    print(f"[YUGEN] ✓ {len(links)} páginas extraídas")
                    return Pages(ch.id, ch.number, ch.name, links)
            
            print("[YUGEN] ✗ Nenhuma página encontrada")
            return Pages(ch.id, ch.number, ch.name, [])
            
        except Exception as e:
            print(f"[YUGEN] ✗ Erro: {e}")
            import traceback
            traceback.print_exc()
            return Pages(ch.id, ch.number, ch.name, [])