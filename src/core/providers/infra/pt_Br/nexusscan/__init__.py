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
    domain = ['nexustoons.site']

    def __init__(self):
        self.url = 'https://nexustoons.site/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.item-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.api_chapters = 'https://nexustoons.site/api/'
    
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
        except Exception as e:
            raise ValueError(f"Erro ao buscar capítulos via AJAX: {e}")

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
        try:
            # Método 1: Captura do script JSON com id="page-data"
            uri = urljoin(self.url, ch.id)
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Procura pelo script com id="page-data"
            page_data_script = soup.find('script', {'id': 'page-data', 'type': 'application/json'})
            
            if page_data_script and page_data_script.string:
                try:
                    # Parse do JSON
                    pages_data = json.loads(page_data_script.string.strip())
                    
                    # Extrai as URLs das imagens ordenadas por page_number
                    img_urls = [page['image_url'] for page in sorted(pages_data, key=lambda x: x['page_number'])]
                    
                    if img_urls:
                        number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
                        print(f"[NEXUSSCAN] ✓ {len(img_urls)} páginas obtidas via script#page-data")
                        return Pages(ch.id, number, ch.name, img_urls)
                except json.JSONDecodeError as e:
                    print(f"[NEXUSSCAN] ✗ Erro ao parsear JSON do script#page-data: {e}")
            
            # Método 2: Captura do script JSON com id="stream-blob-source" (formato novo)
            stream_blob_script = soup.find('script', {'id': 'stream-blob-source', 'type': 'application/json'})
            
            if stream_blob_script and stream_blob_script.string:
                try:
                    # Parse do JSON
                    pages_data = json.loads(stream_blob_script.string.strip())
                    
                    # Extrai as URLs das imagens ordenadas por page_number
                    img_urls = [page['image_url'] for page in sorted(pages_data, key=lambda x: x['page_number'])]
                    
                    if img_urls:
                        number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
                        print(f"[NEXUSSCAN] ✓ {len(img_urls)} páginas obtidas via script#stream-blob-source")
                        return Pages(ch.id, number, ch.name, img_urls)
                except json.JSONDecodeError as e:
                    print(f"[NEXUSSCAN] ✗ Erro ao parsear JSON do script#stream-blob-source: {e}")
            
            # Método 3: Fallback - API (método antigo)
            uri = str(ch.id)
            if uri.startswith("/manga/"):
                uri = uri.replace("/manga/", "page-data/", 1)
            elif uri.startswith("manga/"):
                uri = uri.replace("manga/", "page-data/", 1)
            else:
                print(f"⚠️ Padrão inesperado em ch.id: {uri}")
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

            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            
            if list:
                print(f"[NEXUSSCAN] ✓ {len(list)} páginas obtidas via API (fallback)")
                return Pages(ch.id, number, ch.name, list)
            else:
                print(f"[NEXUSSCAN] ✗ Nenhuma página encontrada")
                return Pages(ch.id, number, ch.name, [])
                
        except Exception as e:
            print(f"[NEXUSSCAN] ✗ Erro ao obter páginas: {e}")
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            return Pages(ch.id, number, ch.name, [])
    
    def _get_chapters_ajax(self, manga_id):
        # https://nexustoons.site/ajax/load-chapters/?item_slug=missoes-na-vida-real&page=1&sort=desc&q=
        title = manga_id.split('/')[-2]
        page = 1
        all_chapters = []
        seen_hrefs = set()
        
        while True:
            uri = f'https://nexustoons.site/ajax/load-chapters/?item_slug={title}&page={page}&sort=desc&q='
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            
            # Parse do HTML retornado
            soup = BeautifulSoup(response.content, 'html.parser')
            # Busca todos os links de capítulos
            chapter_links = soup.select('a')
            
            if not chapter_links:
                print(f"[NEXUSSCAN] Nenhum capítulo encontrado na página {page}")
                break
            
            # Detecta repetições para parar o loop
            repeated_count = 0
            new_chapters_count = 0
            
            for link in chapter_links:
                href = link.get('href', '').strip()
                chapter_number = link.get('data-chapter-number', '').strip()
                
                # Remove caracteres de escape
                chars_to_remove = ['"', '\\n', '\\', '\r', '\t', "'"]
                for char in chars_to_remove:
                    chapter_number = chapter_number.replace(char, '')
                    href = href.replace(char, '')
                
                # Verifica se já vimos este capítulo
                if href in seen_hrefs:
                    repeated_count += 1
                    continue
                
                seen_hrefs.add(href)
                new_chapters_count += 1
                
                # Cria um dicionário compatível com o formato esperado
                chapter_data = {
                    'href': href,
                    'data-chapter-number': chapter_number
                }
                all_chapters.append(chapter_data)
            
            # Se mais de 80% são repetições ou nenhum novo, para o loop
            if len(chapter_links) > 0 and (repeated_count >= len(chapter_links) * 0.8 or new_chapters_count == 0):
                print("[NEXUSSCAN] Parando: muitas repetições detectadas")
                break
            
            page += 1
            
            # Proteção contra loop infinito
            if page > 100:
                print("[NEXUSSCAN] Limite de páginas atingido (100)")
                break
        
        if all_chapters:
            return all_chapters
        else:
            raise ValueError('No chapters found (ajax pagination)!')