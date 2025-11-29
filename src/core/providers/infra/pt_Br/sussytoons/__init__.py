import re
import time
import random
import json
from typing import List
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.config.login_data import insert_login, LoginData, get_login, delete_login

class VerdinhaProvider(Base):
    name = 'verdinha'
    lang = 'pt_Br'
    domain = ['verdinha.wtf']
    has_login = True

    def __init__(self) -> None:
        self.base = 'https://api.verdinha.wtf'
        self.CDN = 'https://cdn.verdinha.wtf'
        self.old = 'https://oldi.verdinha.wtf/wp-content/uploads/WP-manga/data/'
        self.oldCDN = 'https://oldi.verdinha.wtf/scans/1/obras'
        self.webBase = 'https://verdinha.wtf/'
        self.domain_name = 'verdinha.wtf'
        self.access_token = None
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
            "referer": "https://verdinha.wtf/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }
        # Carrega token salvo se existir
        self._load_token()
    
    def _load_token(self):
        """Carrega o token de acesso salvo no banco de dados"""
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            self.access_token = login_info.headers.get('authorization').replace('Bearer ', '')
            self.headers['authorization'] = f'Bearer {self.access_token}'
            print("[Verdinha] ✅ Token de acesso carregado")
    
    def _save_token(self, token: str):
        """Salva o token de acesso no banco de dados"""
        self.access_token = token
        self.headers['authorization'] = f'Bearer {token}'
        insert_login(LoginData(
            self.domain_name,
            {'authorization': f'Bearer {token}'},
            {}
        ))
        print("[Verdinha] ✅ Token de acesso salvo")
    
    def login(self):
        """Realiza login na API da Verdinha"""
        # Verifica se já tem token válido
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            print("[Verdinha] ✅ Login encontrado em cache")
            self._load_token()
            return True
        
        print("[Verdinha] 🔐 Realizando login...")
        
        try:
            login_url = f'{self.base}/auth/login'
            
            # Credenciais de login
            payload = {
                "login": "wallacesouzarocha@gmail.com",
                "senha": "majorw12.",
                "tipo_usuario": "usuario"
            }
            
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "pt-BR,pt;q=0.6",
                "content-type": "application/json",
                "priority": "u=1, i",
                "scan-id": "1",
                "sec-ch-ua": '"Chromium";v="142", "Brave";v="142", "Not_A Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "sec-gpc": "1",
                "referer": "https://verdinha.wtf/"
            }
            
            response = Http.post(
                login_url,
                data=json.dumps(payload),
                headers=headers,
                timeout=15
            )
            
            if response.status in [200, 201]:
                data = response.json()
                access_token = data.get('access_token')
                user = data.get('user', {})
                
                if access_token:
                    self._save_token(access_token)
                    print(f"[Verdinha] ✅ Login bem-sucedido! Usuário: {user.get('nome', 'Desconhecido')}")
                    return True
                else:
                    print("[Verdinha] ❌ Token não encontrado na resposta")
                    return False
            else:
                print(f"[Verdinha] ❌ Falha no login - Status: {response.status}")
                print(f"[Verdinha] Resposta: {response.content}")
                return False
                
        except Exception as e:
            print(f"[Verdinha] ❌ Erro ao fazer login: {e}")
            return False
    
    def getManga(self, link: str) -> Manga:
        try:
            # Verifica se tem token, se não faz login
            if not self.access_token:
                self.login()
            
            # Extrai o slug da obra da URL
            match = re.search(r'/obra/([^/?]+)', link)
            if not match:
                raise Exception("Slug da obra não encontrado na URL")
                
            slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
            api_url = f'{self.base}/obras/{slug}'
            print(f"[Verdinha] Chamando API: {api_url}")
            
            response = Http.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            
            title = data.get('obr_nome', 'Título Desconhecido')
            return Manga(link, title)
            
        except Exception as e:
            print(f"[Verdinha] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        try:
            # Verifica se tem token, se não faz login
            if not self.access_token:
                self.login()
            
            # Extrai o slug da obra da URL
            match = re.search(r'/obra/([^/?]+)', manga_id)
            if not match:
                raise Exception("Slug da obra não encontrado")
                
            slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
            api_url = f'{self.base}/obras/{slug}'
            print(f"[Verdinha] Chamando API: {api_url}")
            
            response = Http.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            
            title = data.get('obr_nome', 'Título Desconhecido')
            chapters_list = []
            for ch in data.get('capitulos', []):
                # Agora armazena [slug, cap_id] para manter compatibilidade
                chapters_list.append(Chapter([slug, ch['cap_id']], ch['cap_nome'], title))
            return chapters_list
        except Exception as e:
            print(f"[Verdinha] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Obter páginas usando apenas API"""
        # Verifica se tem token, se não faz login
        if not self.access_token:
            self.login()
        
        images = []
        
        print(f"[Verdinha] Obtendo páginas para: {ch.name}")
        
        time.sleep(random.uniform(0.3, 1))  # Pequena espera para evitar bloqueios
        try:
            # Usar API com Http
            api_url = f"{self.base}/capitulos/{ch.id[1]}"
            print(f"[Verdinha] Chamando API: {api_url}")
            
            response = Http.get(api_url, headers=self.headers)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            print(data)
            obra_id = data.get('obr_id', 'Desconhecido')
            cap_numero = data.get('cap_numero', 'Desconhecido')
            print(f"[Verdinha] API retornou {len(data.get('cap_paginas', []))} páginas")

            def clean_path(p):
                return p.strip('/') if p else ''

            for i, pagina in enumerate(data.get('cap_paginas', [])):
                try:
                    mime = pagina.get('mime')
                    path = clean_path(pagina.get('path', 'false'))
                    src = clean_path(pagina.get('src', ''))
                    
                    if mime is not None:
                        # Novo formato CDN
                        full_url = f"https://cdn.verdinha.site/wp-content/uploads/WP-manga/data/{src}"
                    elif path == 'false' or path == '' or path is None or path.lower() == 'none':
                        full_url = f"https://cdn.verdinha.wtf/scans/1/obras/{obra_id}/capitulos/{cap_numero}/{src}"
                    else:
                        if 'jpg' in path.lower() or 'png' in path.lower() or 'jpeg' in path.lower() or 'webp' in path.lower():
                            full_url = f"{self.CDN}/{path}"
                        else:
                            full_url = f"{self.CDN}/{path}/{src}"
                    
                    if full_url and full_url.startswith('http'):
                        images.append(full_url)
                        print(f"[Verdinha] Página {i+1}: {full_url}")
                    
                except Exception as e:
                    print(f"[Verdinha] Erro ao processar página {i+1}: {e}")
                    continue
            
            if images:
                print(f"[Verdinha] ✅ Sucesso: {len(images)} páginas encontradas")
                return Pages(ch.id, ch.number, ch.name, images)
            else:
                print("[Verdinha] ⚠️ Nenhuma página válida encontrada")
                
        except Exception as e:
            print(f"[Verdinha] ❌ Erro na API: {e}")

        # Se chegou aqui, API falhou - retornar páginas vazias
        print("[Verdinha] ❌ Falha na API - retornando lista vazia")
        return Pages(ch.id, ch.number, ch.name, [])
