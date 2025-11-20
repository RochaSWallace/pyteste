import re
import time
import random
import requests
from typing import List
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

class NewSussyToonsProvider(Base):
    name = 'New Sussy Toons'
    lang = 'pt_Br'
    domain = ['new.sussytoons.site', 'www.sussyscan.com', 'www.sussytoons.site', 'www.sussytoons.wtf', 'sussytoons.wtf']

    def __init__(self) -> None:
        self.base = 'https://api2.sussytoons.wtf'
        self.CDN = 'https://cdn.sussytoons.site'
        self.old = 'https://oldi.sussytoons.site/wp-content/uploads/WP-manga/data/'
        self.oldCDN = 'https://oldi.sussytoons.site/scans/1/obras'
        self.webBase = 'https://www.sussytoons.wtf'
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=1, i",
            "scan-id": "1",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "referer": "https://www.sussytoons.wtf/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }
    def getManga(self, link: str) -> Manga:
        try:
            # Extrai o slug da obra da URL
            match = re.search(r'/obra/([^/?]+)', link)
            if not match:
                raise Exception("Slug da obra não encontrado na URL")
                
            slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
            api_url = f'{self.base}/obras/{slug}'
            print(f"[SussyToons] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            
            title = data.get('obr_nome', 'Título Desconhecido')
            return Manga(link, title)
            
        except Exception as e:
            print(f"[SussyToons] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        try:
            # Extrai o slug da obra da URL
            match = re.search(r'/obra/([^/?]+)', manga_id)
            if not match:
                raise Exception("Slug da obra não encontrado")
                
            slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
            api_url = f'{self.base}/obras/{slug}'
            print(f"[SussyToons] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            
            title = data.get('obr_nome', 'Título Desconhecido')
            chapters_list = []
            for ch in data.get('capitulos', []):
                # Agora armazena [slug, cap_id] para manter compatibilidade
                chapters_list.append(Chapter([slug, ch['cap_id']], ch['cap_nome'], title))
            return chapters_list
        except Exception as e:
            print(f"[SussyToons] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Obter páginas usando apenas API"""
        images = []
        
        print(f"[SussyToons] Obtendo páginas para: {ch.name}")
        
        time.sleep(random.uniform(0.3, 1))  # Pequena espera para evitar bloqueios
        try:
            # Usar API com requests
            api_url = f"{self.base}/capitulos/{ch.id[1]}"
            print(f"[SussyToons] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            obra_id = data.get('obr_id', 'Desconhecido')
            cap_numero = data.get('cap_numero', 'Desconhecido')
            print(f"[SussyToons] API retornou {len(data.get('cap_paginas', []))} páginas")

            def clean_path(p):
                return p.strip('/') if p else ''

            for i, pagina in enumerate(data.get('cap_paginas', [])):
                try:
                    mime = pagina.get('mime')
                    path = clean_path(pagina.get('path', 'false'))
                    src = clean_path(pagina.get('src', ''))
                    
                    if mime is not None:
                        # Novo formato CDN
                        full_url = f"https://cdn.sussytoons.site/wp-content/uploads/WP-manga/data/{src}"
                    elif path == 'false' or path == '' or path is None or path.lower() == 'none':
                        # https://cdn.sussytoons.wtf/scans/1/obras/9003/capitulos/1/1.jpg
                        # https://cdn.sussytoons.wtf/scans/1/obras/137600/capitulos/1/1.jpg
                        full_url = f"https://cdn.sussytoons.wtf/scans/1/obras/{obra_id}/capitulos/{cap_numero}/{src}"
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
                
        except Exception as e:
            print(f"[SussyToons] ❌ Erro na API: {e}")

        # Se chegou aqui, API falhou - retornar páginas vazias
        print("[SussyToons] ❌ Falha na API - retornando lista vazia")
        return Pages(ch.id, ch.number, ch.name, [])
