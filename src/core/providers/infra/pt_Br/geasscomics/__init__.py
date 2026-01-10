import re
import time
import json
import os
import math
import base64
import requests
import cv2
import numpy as np
from pathlib import Path
from typing import List
from PIL import Image
from io import BytesIO
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.download.domain.dowload_entity import Chapter as DownloadedChapter
from core.config.img_conf import get_config
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.config.login_data import insert_login, LoginData, get_login, delete_login
from core.__seedwork.infra.http import Http

class GeassComicsProvider(Base):
    name = 'Geass Comics'
    lang = 'pt_Br'
    domain = ['geasscomics.xyz']
    has_login = True

    # Constantes de criptografia
    ENCRYPTION_KEY = "4f8d2a7b9c6e1f3a5b0c9e2d7a6b1c3f8e4d2a9b7c6f1e3a5b0c9d2e7f6a1b39"
    SALT = b"manga-app-salt"

    def __init__(self) -> None:
        self.url = 'https://geasscomics.xyz'
        self.login_url = 'https://geasscomics.xyz/api/visitor/auth/login'
        self.domain_key = 'geasscomics.xyz'
        self.timeout = 20
        self.max_paginas = 50

    def login(self):
        """Login via API - retorna token JWT para uso em requisições"""
        # Verifica se já tem login salvo (não faz requisições aqui)
        login_info = get_login(self.domain_key)
        if login_info:
            print("[GeassComics] ✅ Login encontrado em cache")
            return True
        
        print("[GeassComics] ⚠️  Nenhum login encontrado")
        print("[GeassComics] 📝 Tentando fazer login...")
        
        # Tenta fazer login via API
        try:
            login_data = {
                "email": "opai@gmail.com",
                "password": "Opai@123"
            }
            
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "pt-BR,pt;q=0.8",
                "content-type": "application/json",
                "sec-ch-ua": '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "sec-gpc": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.post(
                self.login_url,
                json=login_data,
                headers=headers,
                timeout=15
            )
            
            # Se status OK, salva o token JWT
            if response.status_code == 200:
                data = response.json()
                
                # Extrai o token JWT da resposta
                jwt_token = data.get('jwt', {}).get('token')
                
                if jwt_token:
                    # Salva o token como header personalizado
                    headers_to_save = {
                        'Authorization': f'Bearer {jwt_token}'
                    }
                    
                    insert_login(LoginData(self.domain_key, headers_to_save, {}))
                    
                    visitor_info = data.get('visitor', {})
                    print(f"[GeassComics] ✅ Login bem-sucedido!")
                    print(f"[GeassComics] 👤 Usuário: {visitor_info.get('firstName', 'N/A')}")
                    print(f"[GeassComics] 💎 VIP: {'Sim' if visitor_info.get('vip') else 'Não'}")
                    return True
                else:
                    print("[GeassComics] ⚠️  Token não encontrado na resposta")
                    return False
            else:
                print(f"[GeassComics] ⚠️  Falha no login - Status: {response.status_code}")
                return False
            
        except Exception as e:
            print(f"[GeassComics] ⚠️  Erro no login automático: {e}")
            print("[GeassComics] 💡 O provider funcionará para conteúdo público")
            return False
    def _derive_key(self, password: str) -> bytes:
        """Deriva a chave AES usando PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.SALT,
            iterations=30000,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    def _decrypt_image(self, encrypted_data: bytes, password: str) -> bytes:
        """Descriptografa os dados da imagem usando AES-GCM"""
        key = self._derive_key(password)
        iv = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext

    def _detect_format(self, data: bytes) -> str:
        """Detecta o formato da imagem pelos magic bytes"""
        if data.startswith(b'\xff\xd8\xff'):
            return '.jpg'
        elif data.startswith(b'\x89PNG'):
            return '.png'
        elif data.startswith(b'GIF'):
            return '.gif'
        elif data.startswith(b'RIFF') and b'WEBP' in data[:20]:
            return '.webp'
        return '.bin'


    def getManga(self, link: str) -> Manga:
        """Extrai informações básicas da obra via API"""
        try:
            # Extrai ID da obra da URL
            match = re.search(r'/obra/(\d+)', link)
            if not match:
                raise Exception("ID da obra não encontrado na URL")
            
            obra_id = int(match.group(1))
            
            print(f"[GeassComics] Acessando API da obra: {obra_id}")
            
            # Busca informações via API
            api_url = f"https://geasscomics.xyz/api/manga/{obra_id}"
            
            # Obtém headers com token se disponível
            login_info = get_login(self.domain_key)
            headers = login_info.headers if login_info else {}
            
            response = Http.get(api_url, headers=headers)
            data = response.json()
            
            title = data.get('title', f"Obra {obra_id}")
            
            print(f"[GeassComics] Título: {title}")
            
            return Manga(link, title)
                
        except Exception as e:
            print(f"[GeassComics] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        """Extrai todos os capítulos via API"""
        try:
            # Extrai ID da obra
            match = re.search(r'/obra/(\d+)', manga_id)
            if not match:
                raise Exception("ID da obra não encontrado")
            
            obra_id = int(match.group(1))
            
            print(f"[GeassComics] Extraindo capítulos via API da obra: {obra_id}")
            
            # Busca capítulos via API
            api_url = f"https://geasscomics.xyz/api/manga/{obra_id}/chapter?offset=0&limit=10000&sortOrder=desc"
            
            # Obtém headers com token se disponível
            login_info = get_login(self.domain_key)
            headers = login_info.headers if login_info else {}
            
            response = Http.get(api_url, headers=headers)
            data = response.json()
            
            items = data.get('items', [])
            
            if not items:
                print(f"[GeassComics] Nenhum capítulo encontrado")
                return []
            
            print(f"[GeassComics] ✓ {len(items)} capítulos encontrados")
            
            # Busca título da obra via API
            manga_api_url = f"https://geasscomics.xyz/api/manga/{obra_id}"
            manga_response = Http.get(manga_api_url, headers=headers)
            manga_data = manga_response.json()
            manga_title = manga_data.get('title', f"Obra {obra_id}")
            
            # Converte para objetos Chapter
            chapters_list = []
            for item in items:
                chapter_number = item.get('chapter')
                chapter_title = item.get('title', f"Capítulo {chapter_number}")
                
                # Monta a URL do capítulo
                # Formato: https://geasscomics.xyz/obra/652/capitulo/19
                # chapter_number pode ser float (19.0), então converte para int
                chapter_num_int = int(chapter_number) if chapter_number else 0
                chapter_url = f"{self.url}/obra/{obra_id}/capitulo/{chapter_num_int}"
                
                chapters_list.append(
                    Chapter(
                        chapter_url,
                        str(chapter_num_int),
                        manga_title
                    )
                )
            
            # Reverte a ordem (API retorna desc, mas queremos asc)
            chapters_list.reverse()
            
            return chapters_list
                
        except Exception as e:
            print(f"[GeassComics] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai URLs das páginas de um capítulo via API"""
        try:
            print(f"[GeassComics] Extraindo páginas: {ch.name}")
            
            # Extrai obra_id e capitulo_numero da URL
            # Formato: https://geasscomics.xyz/obra/652/capitulo/19
            match = re.search(r'/obra/(\d+)/capitulo/(\d+)', ch.id)
            if not match:
                raise Exception("IDs não encontrados na URL do capítulo")
            
            obra_id = int(match.group(1))
            capitulo_numero = int(match.group(2))
            
            print(f"[GeassComics] Obra ID: {obra_id}, Capítulo: {capitulo_numero}")
            
            # Busca imagens via API
            # Formato: https://geasscomics.xyz/api/manga/652/chapter/19/images
            api_url = f"https://geasscomics.xyz/api/manga/{obra_id}/chapter/{capitulo_numero}/images"
            
            # Obtém headers com token se disponível
            login_info = get_login(self.domain_key)
            headers = {}
            if login_info and login_info.headers:
                headers.update(login_info.headers)
            
            # Adiciona header obrigatório
            headers['x-mymangas-secure-panel-domain'] = 'true'
            
            response = Http.get(api_url, headers=headers)
            images = response.json()
            
            # A API retorna diretamente um array de URLs
            if not isinstance(images, list):
                raise Exception("Resposta da API não é uma lista")
            
            print(f"[GeassComics] ✓ {len(images)} páginas encontradas")
            
            return Pages(ch.id, ch.number, ch.name, images)
                
        except Exception as e:
            print(f"[GeassComics] Erro em getPages: {e}")
            import traceback
            traceback.print_exc()
            return Pages(ch.id, ch.number, ch.name, [])

    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        """
        Download de imagens do GeassComics.
        Baixa e descriptografa imagens usando AES-GCM.
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        files = []
        total_pages = len(pages.pages)
        
        # Extrai obra_id e capitulo_numero da URL
        match = re.search(r'/obra/(\d+)/capitulo/(\d+)', pages.id)
        if not match:
            print(f"[GeassComics] ✗ Erro: Não foi possível extrair IDs da URL")
            return DownloadedChapter(pages.number, files)
        
        obra_id = int(match.group(1))
        capitulo_numero = int(match.group(2))
        chapter_str = f"{capitulo_numero}.00"
        
        print(f"[GeassComics] Baixando e descriptografando {total_pages} imagens...")
        
        # Obtém headers com token
        login_info = get_login(self.domain_key)
        request_headers = {}
        if login_info and login_info.headers:
            request_headers.update(login_info.headers)
        
        request_headers['x-mymangas-secure-panel-domain'] = 'true'
        request_headers['referer'] = f"https://geasscomics.xyz/obra/{obra_id}/capitulo/{capitulo_numero}"
        
        success = 0
        
        for page_idx in range(total_pages):
            # Sistema de retry para erros 500
            max_retries = 6
            retry_count = 0
            downloaded = False
            
            while retry_count < max_retries and not downloaded:
                try:
                    retry_msg = f" (tentativa {retry_count + 1}/{max_retries})" if retry_count > 0 else ""
                    print(f"[GeassComics] [{page_idx + 1}/{total_pages}] Baixando página {page_idx}{retry_msg}...", end=" ", flush=True)
                    
                    # URL da imagem criptografada
                    url = f"https://geasscomics.xyz/api/manga/{obra_id}/chapter/{chapter_str}/image/{page_idx}"
                    
                    # Baixa imagem criptografada
                    response = requests.get(url, headers=request_headers, timeout=30)
                    response.raise_for_status()
                    
                    # Descriptografa
                    encrypted_data = response.content
                    decrypted = self._decrypt_image(encrypted_data, self.ENCRYPTION_KEY)
                    
                    # Detecta formato e salva
                    ext = self._detect_format(decrypted)
                    if ext == '.bin':
                        ext = img_format  # Usa formato configurado se não detectar
                    
                    file_path = os.path.join(path, f"%03d{ext}" % (page_idx + 1))
                    
                    # Salva imagem descriptografada
                    with open(file_path, 'wb') as f:
                        f.write(decrypted)
                    
                    files.append(file_path)
                    success += 1
                    downloaded = True
                    
                    print(f"✅")
                    
                    # Atualiza progresso
                    if fn is not None:
                        fn(math.ceil((page_idx + 1) * 100) / total_pages)
                    
                except requests.exceptions.HTTPError as e:
                    # Erro HTTP (500, 404, etc)
                    if e.response.status_code == 500 and retry_count < max_retries - 1:
                        # Erro 500 - tenta novamente com backoff exponencial
                        wait_time = 2 ** retry_count  # 1s, 2s, 4s
                        print(f"⚠️ Erro 500, aguardando {wait_time}s...")
                        time.sleep(wait_time)
                        retry_count += 1
                    else:
                        # Outro erro HTTP ou esgotou retries
                        print(f"❌ Erro: {e}")
                        break
                        
                except Exception as e:
                    # Outros erros (descriptografia, I/O, etc)
                    print(f"❌ Erro: {e}")
                    break
        
        print(f"[GeassComics] Download concluído: {success}/{total_pages} imagens")
        
        # Gera erro se alguma página falhou
        if success < total_pages:
            raise Exception(f"Falha ao baixar capítulo: apenas {success}/{total_pages} imagens foram baixadas")
        
        return DownloadedChapter(pages.number, files)
