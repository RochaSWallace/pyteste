import re
import json
import requests
from typing import List
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.config.login_data import insert_login, LoginData, get_login

class KuromangasProvider(Base):
    name = 'Kuromangas'
    lang = 'pt_Br'
    domain = ['beta.kuromangas.com']
    has_login = True

    def __init__(self) -> None:
        self.base = 'https://beta.kuromangas.com'
        self.api_base = 'https://beta.kuromangas.com/api'
        self.cdn = 'https://cdn.kuromangas.com'
        self.domain_name = 'beta.kuromangas.com'
        self.access_token = None
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "pt-BR,pt;q=0.7",
            "content-type": "application/json",
            "sec-ch-ua": '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "referer": self.base
        }
        # Carrega token salvo se existir
        self._load_token()
    
    def _load_token(self):
        """Carrega o token de acesso salvo no banco de dados"""
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            self.access_token = login_info.headers.get('authorization').replace('Bearer ', '')
            self.headers['authorization'] = f'Bearer {self.access_token}'
            print("[Kuromangas] ✅ Token de acesso carregado")
    
    def _save_token(self, token: str):
        """Salva o token de acesso no banco de dados"""
        self.access_token = token
        self.headers['authorization'] = f'Bearer {token}'
        insert_login(LoginData(
            self.domain_name,
            {'authorization': f'Bearer {token}'},
            {}
        ))
        print("[Kuromangas] ✅ Token de acesso salvo")
    
    def login(self):
        """Realiza login na API do Kuromangas"""
        # Verifica se já tem token válido
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            print("[Kuromangas] ✅ Login encontrado em cache")
            self._load_token()
            return True
        
        print("[Kuromangas] 🔐 Realizando login...")
        
        try:
            login_url = f'{self.api_base}/auth/login'
            
            # Credenciais de login
            payload = {
                "email": "opai@gmail.com",
                "password": "Opai@123"
            }
            
            response = Http.post(
                login_url,
                data=json.dumps(payload),
                headers=self.headers,
                timeout=15
            )
            
            if response.status in [200, 201]:
                data = response.json()
                token = data.get('token')
                user = data.get('user', {})
                
                if token:
                    self._save_token(token)
                    print(f"[Kuromangas] ✅ Login bem-sucedido! Usuário: {user.get('username', 'Desconhecido')}")
                    return True
                else:
                    print("[Kuromangas] ❌ Token não encontrado na resposta")
                    return False
            else:
                print(f"[Kuromangas] ❌ Falha no login - Status: {response.status}")
                return False
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro ao fazer login: {e}")
            return False
    
    def getManga(self, link: str) -> Manga:
        """Extrai informações do mangá via API"""
        try:
            # Verifica se tem token, se não faz login
            if not self.access_token:
                self.login()
            
            # Extrair ID do mangá da URL
            # Formato: https://beta.kuromangas.com/manga/1753
            match = re.search(r'/manga/(\d+)', link)
            if not match:
                raise Exception("ID do mangá não encontrado na URL")
                
            manga_id = match.group(1)
            
            api_url = f'{self.api_base}/mangas/{manga_id}'
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                manga_data = data.get('manga', {})
                title = manga_data.get('title', 'Título Desconhecido')
                print(f"[Kuromangas] Mangá encontrado: {title}")
                return Manga(link, title)
            else:
                raise Exception(f"API retornou status {response.status_code}")
            
        except Exception as e:
            print(f"[Kuromangas] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        """Extrai lista de capítulos via API"""
        try:
            # Verifica se tem token, se não faz login
            if not self.access_token:
                self.login()
            
            # Extrair ID do mangá
            match = re.search(r'/manga/(\d+)', manga_id)
            if not match:
                raise Exception("ID do mangá não encontrado")
                
            manga_num_id = match.group(1)
            
            api_url = f'{self.api_base}/mangas/{manga_num_id}'
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            data = response.json()
            
            manga_data = data.get('manga', {})
            title = manga_data.get('title', 'Título Desconhecido')
            
            chapters_list = []
            for ch in data.get('chapters', []):
                chapter_id = ch['id']
                chapter_number = ch.get('chapter_number', 'Desconhecido')
                if '.00' in chapter_number:
                    chapter_number = chapter_number.replace('.00', '')
                elif chapter_number.endswith('0'):
                    chapter_number = chapter_number[:-1]
                
                chapters_list.append(Chapter(chapter_id, chapter_number, title))
            
            print(f"[Kuromangas] Encontrados {len(chapters_list)} capítulos")
            return chapters_list
            
        except Exception as e:
            print(f"[Kuromangas] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai páginas/imagens do capítulo via API"""
        # Verifica se tem token, se não faz login
        if not self.access_token:
            self.login()
        
        try:
            api_url = f"{self.api_base}/chapters/{ch.id}"
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            data = response.json()
            
            pages = data.get('pages', [])
            
            # Construir URLs completas das imagens
            image_urls = []
            for page_path in pages:
                # As páginas vêm como /chapters/xxxxx.webp
                full_url = f"{self.cdn}{page_path}"
                image_urls.append(full_url)
            
            print(f"[Kuromangas] ✅ Encontradas {len(image_urls)} páginas")
            return Pages(ch.id, ch.number, ch.name, image_urls)
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro ao buscar páginas: {e}")
            return Pages(ch.id, ch.number, ch.name, [])
