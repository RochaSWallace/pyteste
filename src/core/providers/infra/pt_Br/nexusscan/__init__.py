from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
import json
import requests
import base64
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

        chapters_data = []
        
        # Tenta primeiro buscar via API JSON (novo formato)
        try:
            ajax_url = self._extract_ajax_url(response.content)
            if ajax_url:
                chapters_data = self._get_chapters_api(ajax_url)
        except Exception:
            pass
        
        # Se não conseguiu via API, tenta via AJAX HTML (formato antigo)
        if not chapters_data:
            try:
                chapters_data = self._get_chapters_ajax(id)
            except Exception as e:
                raise ValueError(f"Erro ao buscar capítulos via AJAX: {e}")

        chs = []
        for el in chapters_data:
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
    
    def _get_chapters_api(self, ajax_url):
        """
        Busca capítulos via API JSON (novo formato com URL criptografada).
        Retorna lista de dicionários com 'href' e 'data-chapter-number'.
        """
        page = 1
        all_chapters = []
        seen_hrefs = set()
        
        while True:
            # Monta a URI com a URL criptografada
            base_url = ajax_url.rstrip('/')
            uri = f'https://nexustoons.site{base_url}/?page={page}&sort=desc&q='
            
            print(f"[NEXUSSCAN API] Requisitando página {page}: {uri}")
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            try:
                content = response.content if isinstance(response.content, str) else response.content.decode('utf-8', errors='ignore')
                json_data = json.loads(content)
                
                # Verifica se é o formato esperado
                if not isinstance(json_data, dict):
                    print(f"[NEXUSSCAN API] ✗ Resposta não é um objeto JSON válido")
                    break
                
                if 'chapters' not in json_data:
                    print(f"[NEXUSSCAN API] ✗ Campo 'chapters' não encontrado no JSON")
                    print(f"[NEXUSSCAN API] Campos disponíveis: {list(json_data.keys())}")
                    break
                
                chapters_list = json_data.get('chapters', [])
                print(f"[NEXUSSCAN API] ✓ Encontrados {len(chapters_list)} capítulos na página {page}")
                
                if not chapters_list:
                    if page == 1:
                        print("[NEXUSSCAN API] ⚠️ Nenhum capítulo encontrado na primeira página")
                    break
                
                for chapter_obj in chapters_list:
                    ch_url = chapter_obj.get('url', '').strip()
                    ch_number = str(chapter_obj.get('number', '')).strip()
                    
                    if not ch_url or not ch_number:
                        continue
                    
                    # Verifica duplicatas
                    if ch_url in seen_hrefs:
                        continue
                    
                    seen_hrefs.add(ch_url)
                    
                    # Monta URL completa se necessário
                    if not ch_url.startswith('http'):
                        ch_url = urljoin(self.url, ch_url)
                    
                    all_chapters.append({
                        'href': ch_url,
                        'data-chapter-number': ch_number
                    })
                
                # Verifica paginação
                pagination = json_data.get('pagination', {})
                if not pagination.get('has_next', False):
                    break
                
                page += 1
                
                if page > 100:
                    break
                    
            except (json.JSONDecodeError, Exception):
                break
        
        if all_chapters:
            return all_chapters
        else:
            raise ValueError('No chapters found via API!')
    
    def _extract_ajax_url(self, html_content):
        """
        Extrai a URL criptografada do AJAX para CHAPTERS da página.
        Testa cada URL encontrada para identificar qual retorna a lista de capítulos.
        """
        content = html_content if isinstance(html_content, str) else html_content.decode('utf-8', errors='ignore')
        
        # Procura por TODAS URLs no formato /api/v1/{token} (token Django)
        # Formato pode ser: /api/v1/.eJ... (antigo) ou /api/v1/eyJ... (novo)
        # Padrão: /api/v1/{base64}:{timestamp}:{signature}/
        pattern = r'/api/v1/\.?[A-Za-z0-9_-]+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+/'
        matches = re.findall(pattern, content)
        
        if matches:
            # Remove duplicatas mantendo a ordem
            unique_matches = []
            seen = set()
            for match in matches:
                if match not in seen:
                    unique_matches.append(match)
                    seen.add(match)
            
            # Testa cada URL para encontrar a que retorna capítulos
            for idx, match in enumerate(unique_matches, 1):
                try:
                    test_uri = f'https://nexustoons.site{match}?page=1&sort=desc&q='
                    response = Http.get(test_uri, timeout=getattr(self, 'timeout', None))
                    test_content = response.content if isinstance(response.content, str) else response.content.decode('utf-8', errors='ignore')
                    test_data = json.loads(test_content)
                    
                    # Verifica se retorna lista de capítulos
                    if isinstance(test_data, dict) and 'chapters' in test_data:
                        return match
                        
                except Exception:
                    continue
            
            print("[NEXUSSCAN] ⚠️ Nenhuma URL retornou capítulos após testes")
        
        print("[NEXUSSCAN] ⚠️ URL criptografada não encontrada, usando formato antigo")
        return None
    
    def getPages(self, ch: Chapter) -> Pages:
        try:
            # Método 1: Captura do script JSON com id="page-data"
            uri = urljoin(self.url, ch.id)
            print(f"[NEXUSSCAN] Obtendo páginas para capítulo: {uri}")
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
            
            # Método 3: Busca genérica - qualquer script type="application/json" com image_url e page_number
            json_scripts = soup.find_all('script', {'type': 'application/json'})
            
            print(f"[NEXUSSCAN] 🔍 Encontrados {len(json_scripts)} scripts type='application/json'")
            
            for idx, script in enumerate(json_scripts, 1):
                if not script.string:
                    print(f"[NEXUSSCAN] Script {idx}: sem conteúdo (vazio)")
                    continue
                
                try:
                    # Tenta parsear o JSON
                    data = json.loads(script.string.strip())
                    
                    # Verifica se é uma lista de objetos com page_number e image_url
                    if isinstance(data, list) and len(data) > 0:
                        first_item = data[0]
                        if isinstance(first_item, dict) and 'page_number' in first_item and 'image_url' in first_item:
                            # Extrai as URLs ordenadas
                            img_urls = [page['image_url'] for page in sorted(data, key=lambda x: x['page_number'])]
                            
                            if img_urls:
                                number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
                                script_id = script.get('id', 'sem-id')
                                print(f"[NEXUSSCAN] ✓ {len(img_urls)} páginas obtidas via script genérico (id={script_id})")
                                return Pages(ch.id, number, ch.name, img_urls)
                        else:
                            print(f"[NEXUSSCAN] Script {idx}: lista válida mas sem page_number/image_url")
                    else:
                        print(f"[NEXUSSCAN] Script {idx}: não é lista ou está vazia")
                except json.JSONDecodeError as e:
                    print(f"[NEXUSSCAN] Script {idx}: erro ao parsear JSON - {e}")
                except (KeyError, TypeError) as e:
                    print(f"[NEXUSSCAN] Script {idx}: erro de estrutura - {e}")
                except Exception as e:
                    print(f"[NEXUSSCAN] Script {idx}: erro inesperado - {e}")
                    continue
            
            # Método 4: Fallback - API (método antigo)
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
            img_list = [] 
            while True:
                uri = f"{uri_base}{count}/"
                try:
                    response = Http.get(uri)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    temp = soup.text
                    image = dict(json.loads(temp)).get("image_url")
                    img_list.append(image)
                    count += 1
                except:
                    break

            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            
            if img_list:
                print(f"[NEXUSSCAN] ✓ {len(img_list)} páginas obtidas via API (fallback)")
                return Pages(ch.id, number, ch.name, img_list)
            else:
                print(f"[NEXUSSCAN] ✗ Nenhuma página encontrada")
                return Pages(ch.id, number, ch.name, [])
                
        except Exception as e:
            print(f"[NEXUSSCAN] ✗ Erro ao obter páginas: {e}")
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            return Pages(ch.id, number, ch.name, [])
    
    def _get_chapters_ajax(self, manga_id):
        """
        Busca capítulos via AJAX HTML (formato antigo).
        Retorna lista de dicionários com 'href' e 'data-chapter-number'.
        """
        title = manga_id.split('/')[-2]
        page = 1
        all_chapters = []
        seen_hrefs = set()
        
        while True:
            # Formato antigo com item_slug
            uri = f'https://nexustoons.site/ajax/load-chapters/?item_slug={title}&page={page}&sort=desc&q='
            
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            
            # Parse do HTML retornado (formato antigo)
            soup = BeautifulSoup(response.content, 'html.parser')
            # Busca todos os links de capítulos
            chapter_links = soup.select('a')
            
            if not chapter_links:
                break
            
            # Detecta repetições para parar o loop
            repeated_count = 0
            new_chapters_count = 0
            
            for link in chapter_links:
                href = link.get('href', '').strip()
                chapter_number = link.get('data-chapter-number', '').strip()
                
                # Decodifica base64 se o href usar window.atob()
                # Formato: javascript:window.location.href=window.atob(base64_string) OU window.atob('base64_string')
                if 'window.atob(' in href:
                    try:
                        # Tenta extrair com aspas simples primeiro
                        base64_match = re.search(r"window\.atob\('([^']+)'\)", href)
                        if not base64_match:
                            # Tenta sem aspas (formato direto)
                            base64_match = re.search(r"window\.atob\(([^)]+)\)", href)
                        
                        if base64_match:
                            base64_string = base64_match.group(1)
                            # Decodifica base64 para obter o caminho relativo
                            decoded_path = base64.b64decode(base64_string).decode('utf-8')
                            # O caminho já vem completo com /leitor/...
                            href = decoded_path
                            print(f"[NEXUSSCAN] Link decodificado: {decoded_path}")
                    except Exception as e:
                        print(f"[NEXUSSCAN] ⚠️ Erro ao decodificar base64 do capítulo: {e}")
                        print(f"[NEXUSSCAN] href original: {href}")
                        continue
                
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