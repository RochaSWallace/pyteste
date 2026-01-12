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
    domain = ['nexustoons.com']

    def __init__(self):
        self.url = 'https://nexustoons.com/'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.item-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.api_chapters = 'https://nexustoons.com/api/'

    def getManga(self, link: str) -> Manga:
        """
        Obtém informações da obra via API REST
        URL da obra: https://nexustoons.com/manga/{slug}
        API: https://nexustoons.com/api/manga/{slug}
        """
        # Extrai o slug da URL
        # Exemplo: https://nexustoons.com/manga/private-tutoring-in-these-trying-times
        slug = link.rstrip('/').split('/manga/')[-1]
        
        # Chama a API
        api_url = f"https://nexustoons.com/api/manga/{slug}"
        print(f"[NexusScan] getManga API: {api_url}")
        
        try:
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            data = json.loads(response.content)
            
            title = data.get('title', 'Título Desconhecido')
            print(f"[NexusScan] ✓ Obra encontrada: {title}")
            
            return Manga(id=link, name=title)
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter manga: {e}")
            raise ValueError(f"Erro ao obter informações da obra: {e}")

    def getChapters(self, id: str) -> List[Chapter]:
        """
        Obtém lista de capítulos via API REST
        A mesma API do getManga já retorna todos os capítulos
        URL dos capítulos: https://nexustoons.com/ler/{slug}/{chapter_id}
        """
        # Extrai o slug da URL
        slug = id.rstrip('/').split('/manga/')[-1]
        
        # Chama a API
        api_url = f"https://nexustoons.com/api/manga/{slug}"
        print(f"[NexusScan] getChapters API: {api_url}")
        
        try:
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            data = json.loads(response.content)
            
            title = data.get('title', 'Título Desconhecido')
            chapters_data = data.get('chapters', [])
            
            if not chapters_data:
                print(f"[NexusScan] ⚠️  Nenhum capítulo encontrado para {title}")
                return []
            
            print(f"[NexusScan] ✓ {len(chapters_data)} capítulos encontrados para {title}")
            
            chs = []
            for chapter in chapters_data:
                chapter_id = chapter.get('id')
                chapter_number = str(chapter.get('number', '')).strip()
                
                if not chapter_id or not chapter_number:
                    continue
                
                # Monta a URL do capítulo: https://nexustoons.com/ler/{slug}/{chapter_id}
                ch_url = f"https://nexustoons.com/ler/{slug}/{chapter_id}"
                
                chs.append(Chapter(ch_url, chapter_number, title))
            
            # Inverte para ordem crescente (API retorna decrescente)
            chs.reverse()
            return chs
            
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter capítulos: {e}")
            raise ValueError(f"Erro ao buscar capítulos: {e}")
    
    def getPages(self, ch: Chapter) -> Pages:
        """
        Obtém páginas do capítulo via API REST
        URL do capítulo: https://nexustoons.com/ler/{slug}/{chapter_id}
        API: https://nexustoons.com/api/chapter/{chapter_id}
        """
        try:
            # Extrai o chapter_id da URL
            # Exemplo: https://nexustoons.com/ler/private-tutoring-in-these-trying-times/190265
            chapter_id = ch.id.rstrip('/').split('/')[-1]
            
            # Chama a API
            api_url = f"https://nexustoons.com/api/chapter/{chapter_id}"
            print(f"[NexusScan] getPages API: {api_url}")
            
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            data = json.loads(response.content)
            
            # Extrai as páginas
            pages_data = data.get('pages', [])
            
            if not pages_data:
                print(f"[NexusScan] ⚠️  Nenhuma página encontrada")
                number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
                return Pages(ch.id, number, ch.name, [])
            
            # Ordena por pageNumber e extrai imageUrl
            img_urls = [page['imageUrl'] for page in sorted(pages_data, key=lambda x: x['pageNumber'])]
            
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            print(f"[NexusScan] ✓ {len(img_urls)} páginas obtidas")
            
            return Pages(ch.id, number, ch.name, img_urls)
            
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter páginas: {e}")
            import traceback
            traceback.print_exc()
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            return Pages(ch.id, number, ch.name, [])
