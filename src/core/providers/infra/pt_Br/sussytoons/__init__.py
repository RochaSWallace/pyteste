import re
import requests
import time
import random
import threading
from typing import List
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

# Rate limiting global para evitar sobrecarga do servidor
_LAST_REQUEST_TIME = 0
_REQUEST_LOCK = threading.Lock()
_MIN_INTERVAL = 0.5  # Mínimo 500ms entre requisições

class NewSussyToonsProvider(Base):
    name = 'New Sussy Toons'
    lang = 'pt_Br'
    domain = ['new.sussytoons.site', 'www.sussyscan.com', 'www.sussytoons.site', 'www.sussytoons.wtf', 'sussytoons.wtf']

    def __init__(self) -> None:
        self.base = 'https://api.sussytoons.wtf'
        self.CDN = 'https://cdn.sussytoons.site'
        self.old = 'https://oldi.sussytoons.site/wp-content/uploads/WP-manga/data/'
        self.oldCDN = 'https://oldi.sussytoons.site/scans/1/obras'
        self.webBase = 'https://www.sussytoons.wtf'
        self.cookies = [{'sussytoons-terms-accepted', 'true'}]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': 'https://www.sussytoons.wtf',
            'Referer': 'https://www.sussytoons.wtf/'
        }
    
    def _rate_limited_request(self, url, timeout=30):
        """Faz requisição com rate limiting global para evitar 403"""
        global _LAST_REQUEST_TIME, _REQUEST_LOCK, _MIN_INTERVAL
        
        with _REQUEST_LOCK:
            # Calcula tempo desde última requisição
            current_time = time.time()
            time_since_last = current_time - _LAST_REQUEST_TIME
            
            # Se foi muito rápido, aguarda
            if time_since_last < _MIN_INTERVAL:
                sleep_time = _MIN_INTERVAL - time_since_last
                print(f"[SussyToons] Rate limiting: aguardando {sleep_time:.2f}s")
                time.sleep(sleep_time)
            
            # Atualiza timestamp
            _LAST_REQUEST_TIME = time.time()
        
        # Faz a requisição fora do lock
        session = requests.Session()
        session.headers.update(self.headers)
        
        # Adicionar cookies se necessário
        for cookie in self.cookies:
            if isinstance(cookie, dict):
                for key, value in cookie.items():
                    session.cookies.set(key, value)
        
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        finally:
            session.close()

    def getManga(self, link: str) -> Manga:
        try:
            match = re.search(r'/obra/(\d+)', link)
            if not match:
                raise Exception("ID do mangá não encontrado na URL")
                
            id_value = match.group(1)
            
            response = self._rate_limited_request(f'{self.base}/obras/{id_value}')
            
            data = response.json()
            title = data['resultado']['obr_nome']
            return Manga(link, title)
            
        except Exception as e:
            print(f"[SussyToons] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        try:
            match = re.search(r'/obra/(\d+)', manga_id)
            if not match:
                raise Exception("ID do mangá não encontrado")
                
            id_value = match.group(1)
            
            response = self._rate_limited_request(f'{self.base}/obras/{id_value}')
            
            data = response.json()
            title = data['resultado']['obr_nome']
            chapters_list = []
            for ch in data['resultado']['capitulos']:
                chapters_list.append(Chapter([id_value, ch['cap_id']], ch['cap_nome'], title))
            return chapters_list
        except Exception as e:
            print(f"[SussyToons] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Obter páginas usando apenas API - versão thread-safe"""
        images = []
        
        print(f"[SussyToons] Obtendo páginas para: {ch.name}")
        
        time.sleep(random.uniform(0, 2))  # Pequena espera para evitar bloqueios
        try:
            # Usar API com rate limiting
            response = self._rate_limited_request(f"{self.base}/capitulos/{ch.id[1]}")

            resultado = response.json()['resultado']
            print(f"[SussyToons] API retornou {len(resultado.get('cap_paginas', []))} páginas")

            def clean_path(p):
                return p.strip('/') if p else ''

            for i, pagina in enumerate(resultado.get('cap_paginas', [])):
                try:
                    mime = pagina.get('mime')
                    path = clean_path(pagina.get('path', ''))
                    src = clean_path(pagina.get('src', ''))
                    
                    if mime is not None:
                        # Novo formato CDN
                        full_url = f"https://cdn.sussytoons.site/wp-content/uploads/WP-manga/data/{src}"
                    else:
                        # Formato antigo
                        full_url = f"{self.CDN}/{path}/{src}"
                    
                    if full_url and full_url.startswith('http'):
                        images.append(full_url)
                        print(f"[SussyToons] Página {i+1}: {full_url}")
                    
                except Exception as e:
                    print(f"[SussyToons] Erro ao processar página {i+1}: {e}")
                    continue
            
            if images:
                print(f"[SussyToons] ✅ Sucesso: {len(images)} páginas encontradas")
                return Pages(ch.id, ch.number, ch.name, images)
            else:
                print("[SussyToons] ⚠️ Nenhuma página válida encontrada")
                
        except requests.exceptions.RequestException as e:
            print(f"[SussyToons] ❌ Erro de rede na API: {e}")
        except Exception as e:
            print(f"[SussyToons] ❌ Erro geral na API: {e}")

        # Se chegou aqui, API falhou - retornar páginas vazias
        # Não usar navegador para evitar crashes no "Baixar tudo"
        print("[SussyToons] ❌ Falha na API - retornando lista vazia")
        return Pages(ch.id, ch.number, ch.name, [])
