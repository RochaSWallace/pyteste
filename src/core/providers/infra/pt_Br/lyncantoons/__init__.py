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
import os

class LycanToonsProvider(WordPressMadara):
    name = 'Lycan Toons'
    lang = 'pt-Br'
    domain = ['lycantoons.com']

    def __init__(self):
        self.url = 'https://lycantoons.com/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.item-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        # self.api_chapters = 'https://nexustoons.site/api/'
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link, timeout=getattr(self, 'timeout', None))
        content = response.content if isinstance(response.content, str) else response.content.decode('utf-8', errors='ignore')
        
        title = None
        
        # Busca por qualquer push com JSON Book
        start_marker = 'self.__next_f.push([1,"'
        start_idx = content.find(start_marker)
        
        if start_idx != -1:
            # Avança para depois do marcador inicial
            json_start = start_idx + len(start_marker)
            
            # Procura pelo Book no conteúdo a partir daqui
            book_search = content[json_start:json_start + 10000]  # Busca nos próximos 10k chars
            
            if '\\"@type\\":\\"Book\\"' in book_search:
                
                # Encontra o final do JSON (fecha com "}"])
                end_marker = '"}])'
                end_idx = content.find(end_marker, json_start)
                
                if end_idx != -1:
                    # Extrai a string JSON completa
                    json_str = content[json_start:end_idx]
                    
                    try:
                        # Decodifica o JSON (remove os escapes)
                        json_str_clean = json_str.encode().decode('unicode_escape')
                        data = json.loads(json_str_clean)
                        
                        title = data.get('name')
                    except Exception as e:
                        # Tenta de forma mais direta
                        try:
                            # Simplesmente substitui \" por "
                            json_str_clean = json_str.replace('\\"', '"')
                            data = json.loads(json_str_clean)
                            title = data.get('name')
                        except Exception as e2:
                            print(f"[LycanToons getManga] ✗ Erro no método alternativo: {e2}")
                else:
                    print(f"[LycanToons getManga] ✗ Marcador de fim não encontrado")
            else:
                print(f"[LycanToons getManga] ✗ Book não encontrado no conteúdo após push")
        else:
            print(f"[LycanToons getManga] ✗ Marcador self.__next_f.push não encontrado")
        
        # Fallback: busca direta por padrão simples
        if not title:
            # Busca o trecho que tem o nome do manga
            pattern = r'\\"name\\":\\"([^\\]+?)\\".*?\\"@type\\":\\"Book\\"'
            match = re.search(pattern, content)
            if not match:
                # Tenta inverso
                pattern = r'\\"@type\\":\\"Book\\".*?\\"name\\":\\"([^\\]+?)\\"'
                match = re.search(pattern, content)
            
            if match:
                title = match.group(1)
        
        # Último fallback: meta tags
        if not title:
            soup = BeautifulSoup(content, 'html.parser')
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                title = meta_title.get('content', '').strip()
            else:
                print(f"[LycanToons getManga] ✗ Meta tag og:title não encontrada")
        
        return Manga(id=link, name=title or "Título Desconhecido")

    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        content = response.content if isinstance(response.content, str) else response.content.decode('utf-8', errors='ignore')
        
        title = None
        chapters_data = []
        
        # Busca pelo array "capitulos" completo do Next.js
        capitulos_pattern = r'\\"capitulos\\":\s*\[(.+?)\]'
        capitulos_match = re.search(capitulos_pattern, content, re.DOTALL)
        
        if capitulos_match:
            try:
                capitulos_json_str = '[' + capitulos_match.group(1) + ']'
                capitulos_json_str = capitulos_json_str.replace('\\"', '"')
                capitulos_json_str = capitulos_json_str.replace('\\n', '')
                
                capitulos_array = json.loads(capitulos_json_str)
                
                for cap in capitulos_array:
                    numero = cap.get('numero', '')
                    manga_slug = id.strip('/').split('/')[-1] if '/' in id else id
                    ch_url = f"https://lycantoons.com/series/{manga_slug}/{numero}"
                    
                    if numero:
                        chapters_data.append({
                            'url': ch_url,
                            'number': str(numero)
                        })
            except Exception as e:
                print(f"[LycanToons] Erro ao parsear capitulos: {e}")
        
        # Busca o título
        if not title:
            title_pattern = r'\\"name\\":\\"([^\\]+?)\\".*?\\"@type\\":\\"Book\\"'
            title_match = re.search(title_pattern, content, re.DOTALL)
            if not title_match:
                title_pattern = r'\\"@type\\":\\"Book\\".*?\\"name\\":\\"([^\\]+?)\\"'
                title_match = re.search(title_pattern, content, re.DOTALL)
            
            if title_match:
                title = title_match.group(1)
        
        # FALLBACK: Busca dados do Book com hasPart
        if not chapters_data:
            start_marker = 'self.__next_f.push([1,"'
            start_idx = 0
            
            while True:
                start_idx = content.find(start_marker, start_idx)
                if start_idx == -1:
                    break
                
                json_start = start_idx + len(start_marker)
                chunk = content[json_start:json_start + 15000]
                
                if '\\"@type\\":\\"Book\\"' in chunk and '\\"hasPart\\"' in chunk:
                    end_marker = '"}])'
                    end_idx = content.find(end_marker, json_start)
                    
                    if end_idx != -1:
                        json_str = content[json_start:end_idx]
                        
                        try:
                            json_str_clean = json_str.replace('\\"', '"')
                            json_str_clean = json_str_clean.replace('\\n', '\n')
                            data = json.loads(json_str_clean)
                            
                            if not title:
                                title = data.get('name')
                            
                            has_part = data.get('hasPart', [])
                            
                            for chapter_obj in has_part:
                                ch_name = chapter_obj.get('name', '')
                                ch_url = chapter_obj.get('url', '')
                                
                                ch_number = re.findall(r'\d+\.?\d*', ch_name)
                                ch_number = ch_number[0] if ch_number else ch_name
                                
                                if ch_url and ch_number:
                                    chapters_data.append({
                                        'url': ch_url,
                                        'number': ch_number
                                    })
                            break
                        except Exception:
                            pass
                
                start_idx += 1
        
        # Fallback: regex direto
        if not chapters_data:
            pattern = r'\\"@type\\":\\"Chapter\\".*?\\"name\\":\\"([^\\]+?)\\".*?\\"url\\":\\"(https://[^\\]+?)\\"'
            matches = re.findall(pattern, content, re.DOTALL)
            
            for ch_name, ch_url in matches:
                ch_number = re.findall(r'\d+\.?\d*', ch_name)
                ch_number = ch_number[0] if ch_number else ch_name
                
                if ch_url and ch_number:
                    chapters_data.append({
                        'url': ch_url,
                        'number': ch_number
                    })
        
        # Fallback: método AJAX
        if not chapters_data:
            soup = BeautifulSoup(content, 'html.parser')
            
            if not title:
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    title = meta_title.get('content', '').strip()
            
            try:
                data = self._get_chapters_ajax(id)
                
                for el in data:
                    ch_id = el.get("href", "").strip()
                    ch_number = el.get("data-chapter-number", "").strip()
                    chars_to_remove = ['"', '\\n', '\\', '\r', '\t', "'"]
                    for char in chars_to_remove:
                        ch_number = ch_number.replace(char, "")
                        ch_id = ch_id.replace(char, "")
                    chapters_data.append({'url': ch_id, 'number': ch_number})
            except ValueError as e:
                raise ValueError(f"Erro ao buscar capítulos via AJAX: {e}") from e
        
        # Monta lista de capítulos
        chs = []
        for ch_data in chapters_data:
            chs.append(Chapter(
                ch_data['url'], 
                ch_data['number'], 
                title or "Título Desconhecido"
            ))
        
        chs.reverse()
        return chs
    
    def getPages(self, ch: Chapter) -> Pages:
        """
        Extrai as URLs das imagens do JSON embutido no HTML do Next.js.
        Busca pelo padrão: self.__next_f.push([1,"..."]) que contém imageUrls
        """
        try:
            ch_number = re.findall(r'\d+\.?\d*', str(ch.number))
            number = ch_number[0] if ch_number else ch.number
            
            # Headers seguindo o padrão do fetch
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                'cache-control': 'max-age=0',
                'priority': 'u=0, i',
                'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            }
            
            # Faz requisição HTTP com headers customizados
            response = requests.get(ch.id, headers=headers, timeout=30)
            content = response.text
            
            img_urls = []
            
            # Busca diretamente pelo array imageUrls no HTML
            # O padrão está em: self.__next_f.push([1,"a:[[...],[...{\"imageUrls\":[...]}]]\n"])
            # Tenta vários padrões para encontrar as URLs
            
            # Padrão 1: Busca imageUrls com aspas escapadas ou não
            patterns = [
                r'"imageUrls":\s*\[([^\]]+)\]',  # Padrão genérico
                r'\\"imageUrls\\":\s*\[([^\]]+)\]',  # Com escapes
            ]
            
            urls_str = None
            for pattern in patterns:
                urls_match = re.search(pattern, content)
                if urls_match:
                    urls_str = urls_match.group(1)
                    break
            
            if urls_str:
                # Extrai todas as URLs do conteúdo encontrado
                # Tenta com diferentes padrões de escape
                url_patterns = [
                    r'"(https://cdn\.lycantoons\.com/file/[^"]+)"',  # URLs normais
                    r'\\"(https://cdn\.lycantoons\.com/file/[^\\]+)\\"',  # URLs com escape
                    r'(https://cdn\.lycantoons\.com/file/lycantoons/[^\s,"\]]+)',  # URLs sem aspas
                ]
                
                for url_pattern in url_patterns:
                    img_urls = re.findall(url_pattern, urls_str)
                    if img_urls:
                        # Remove barras invertidas no final das URLs (artefatos de escape)
                        img_urls = [url.rstrip('\\') for url in img_urls]
                        break
            
            return Pages(ch.id, number, ch.name, img_urls if img_urls else [])
                
        except Exception as e:
            print(f"[LycanToons getPages] ✗ Erro ao buscar imagens: {e}")
            import traceback
            traceback.print_exc()
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
                break
            
            page += 1
            
            # Proteção contra loop infinito
            if page > 100:
                break
        
        if all_chapters:
            return all_chapters
        else:
            raise ValueError('No chapters found (ajax pagination)!')