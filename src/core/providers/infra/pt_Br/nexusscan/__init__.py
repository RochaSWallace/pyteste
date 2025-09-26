from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
import json
import requests
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs

class NexusScanProvider(WordPressMadara):
    name = 'Nexus Scan'
    lang = 'pt-Br'
    domain = ['nexusscan.site']

    def __init__(self):
        self.url = 'https://nexusscan.site/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.item-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.api_chapters = 'https://nexusscan.site/api/'
    
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

        try:
            data = self._get_chapters_ajax(id)
        except Exception:
            raise Exception("erro ajax")

        chs = []
        for el in data:
            ch_id = el.get("href", "").strip()
            ch_number = el.get("data-chapter-number", "").strip()
            chars_to_remove = ['"', '\\n', '\\', '\r', '\t', "'"]
            for char in chars_to_remove:
                ch_number = ch_number.replace(char, "")
                ch_id = ch_id.replace(char, "")
            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs
    
    def getPages(self, ch: Chapter) -> Pages:
        # 'https://nexusscan.site/api/page-data/missoes-na-vida-real/172/5/'
        # 
        
        uri = str(ch.id)
        if uri.startswith("/manga/"):
            uri = uri.replace("/manga/", "page-data/", 1)  # Só primeira ocorrência
        elif uri.startswith("manga/"):
            uri = uri.replace("manga/", "page-data/", 1)
        else:
            # Fallback se não encontrar o padrão esperado
            print(f"⚠️ Padrão inesperado em ch.id: {uri}")
            # Tenta extrair o slug do mangá de outra forma
            parts = uri.strip('/').split('/')
            if len(parts) >= 2:
                uri = f"page-data/{'/'.join(parts[1:])}" 
        
        uri_base = f"{self.api_chapters}{uri}"
        count = 1
        list = [] 
        while True:
            uri = f"{uri_base}{count}/"
            try:
                response = Http.get(uri)
                soup = BeautifulSoup(response.content, 'html.parser')
                temp = soup.text
                image = dict(json.loads(temp)).get("image_url")
                list.append(image)
                count += 1
            except:
                break

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, list)
    
    def _get_chapters_ajax(self, manga_id):
        # https://nexusscan.site/ajax/load-chapters/?item_slug=missoes-na-vida-real&page=1&sort=desc&q=
        title = manga_id.split('/')[-2]
        page = 1
        all_chapters = []
        seen_hrefs = set()
        
        while True:
            uri = f'https://nexusscan.site/ajax/load-chapters/?item_slug={title}&page={page}&sort=desc&q='
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
                
            data = self._fetch_dom(response, self.query_chapters)
            
            if not data:
                break
            
            # Detecta repetições para parar o loop
            page_hrefs = set()
            repeated_count = 0
            
            for chapter in data:
                href = chapter.get("href", "")
                if href in seen_hrefs:
                    repeated_count += 1
                else:
                    seen_hrefs.add(href)
                    page_hrefs.add(href)
            
            # Se mais de 50% são repetições, para o loop
            if repeated_count >= len(data) * 0.5:
                break
            
            # Adiciona apenas capítulos novos
            new_chapters = [ch for ch in data if ch.get("href", "") in page_hrefs]
            all_chapters.extend(new_chapters)
            
            page += 1
            
            # Proteção contra loop infinito
            if page > 100:
                break
        
        if all_chapters:
            return all_chapters
        else:
            raise Exception('No chapters found (ajax pagination)!')