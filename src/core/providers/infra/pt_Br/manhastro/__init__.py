import os
import cv2
import json
import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import urljoin
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.application.use_cases import DownloadUseCase
from core.config.login_data import LoginData, get_login, insert_login
from core.providers.infra.template.wordpress_madara import WordPressMadara

class ManhastroProvider(WordPressMadara):
    name = 'Manhastro'
    lang = 'pt-Br'
    domain = ['manhastro.net']
    has_login = True

    def __init__(self):
        self.url = 'https://manhastro.net/'
        self.api_base = 'https://api2.manhastro.net'
        self.path = ''
        self.domain_name = 'manhastro.net'
        self.login_email = 'wsr1@aluno.ifal.edu.br'
        self.login_password = 'majorw12'
        # Token de fallback; pode expirar e ser sobrescrito via variável de ambiente.
        self.turnstile_token = (
            '0.c7IhzkmcXeiYJhG8Bj4CDc3SNODyI1YcSgH7c-smKIPDkvkqFjTtjHBwFd8uG4vk-ETkvsxDyEDg3vvJC3eB4myHD9svBpFhtKclOGPMSSWulsICTzRmHjg9nFZrkdxO5tBzkPbuGJ4xSFk-nix7QXRNcwCjZj3sQ4VtCadZyAwCB2aPQA3Gt-Qt2GEKU5XZOwxwqkG4m2kdWFJ07mxBrQ2xEoipPn9vT9XZXfJIeL3FByPvIR2u_gU9tlnUBYSsjwwwUL441Qa7U10GXR64VRcwRkshy36B8A_vgjaKokViTfHqUpyTNllGZzjPz-nNGz_Q7dpzy8y7Pg1zJkzGuTMSmRuyG4cDKnwvig_mOPB9G1VFnz36n6LwF70lqwQKS-G7eY8y_487tTL_2geQIhnIDiR_C0XSUKrym3mbUjQjYlNvXF0Q9jHcCKaXVMHwWYXfeyVdBsr4UfU0JXDYiuJYVXUsOOjcAIvpyOC5lEQmLhKLkwTW0qhQi-rVyb_0smXH2OgjRHmCXMRT69uxZNXGbnsXEFuapjdSTq637GwXInvGy8b7Yr6lC0gTFVpqGblxFfHjxZtE9PKp45vIEYOr2-niJdhAGRUAU8lzBNUMEUT7Z6rWX-I-uvDlbxUE9Z7UISEI-RGMp91oFwkFJTen7XObV7tMOVpBpGKa3IK7Zajm55e4lxySGLKulJHuryZlJD_tbnRI7W1p9vZ9QsfLb3ZWBAMOV2Erje8E32r3TkWlTfc7hpqdV96HGE3hTXhRCFM68PHtRLzJb9Sz1uV1Vof2PaDf-gsOKDftsWNuGAAYBG4EYwWVbEF7UwxDbdfoS2RSN6uy1x1GaR18vFUAG1qsO6iijRXW_FsRb6fFJ2xC9hqOp1WykW-bCdWsJkEyIVzY9N2lhSx4LFETJK8o88UstKh8ldZam5WaN7E.ho_ibpZuQ81xYIg9GUbE6A.c269a6ea8b36f53521377feda2684c947e1f40f60cdba6201427ec0bdb36e1a2'
        )
        self.access_token = None
        self.timeout = 20
        self.catalog_cache_ttl = 600
        self._catalog_cache_data = None
        self._catalog_cache_at = 0.0
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div.relative > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'img[alt*="Página"]'
        self.query_title_for_uri = 'div.space-y-4 > h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self._load_token()

    def _load_token(self):
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            self.access_token = login_info.headers.get('authorization').replace('Bearer ', '')

    def _save_token(self, token: str):
        self.access_token = token
        insert_login(LoginData(
            domain=self.domain_name,
            headers={'authorization': f'Bearer {token}'},
            cookies={}
        ))

    def _extract_manga_id(self, value: str) -> str | None:
        if not value:
            return None
        digits = re.findall(r'\d+', value)
        return digits[-1] if digits else None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        data = soup.select(self.query_title_for_uri)
        if data:
            element = data.pop()
            return element.get('content', '').strip() or element.text.strip()
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title:
            return og_title.get('content', '').strip()
        h1 = soup.select_one('h1')
        if h1:
            return h1.text.strip()
        return 'Título Desconhecido'

    def _auth_headers(self) -> dict:
        headers = {'accept': 'application/json'}
        if self.access_token:
            headers['authorization'] = f'Bearer {self.access_token}'
        return headers

    def _parse_api_json_text(self, text: str):
        raw = (text or '').strip()
        if raw.startswith('_'):
            raw = raw[1:]
        return json.loads(raw) if raw else {}

    def _get_catalog_data(self, force_refresh=False):
        now = time.time()
        cache_is_valid = (
            self._catalog_cache_data is not None
            and (now - self._catalog_cache_at) < self.catalog_cache_ttl
        )
        if not force_refresh and cache_is_valid:
            return self._catalog_cache_data

        response = requests.get(
            f'{self.api_base}/dados',
            headers=self._auth_headers(),
            timeout=self.timeout
        )
        payload = self._parse_api_json_text(response.text)
        data = payload.get('data', {}) if isinstance(payload, dict) else {}

        self._catalog_cache_data = data
        self._catalog_cache_at = now
        return data

    def _find_manga_in_catalog(self, node, manga_id: str):
        manga_id = str(manga_id)

        if isinstance(node, dict):
            # Alguns catálogos usam a key como id da obra.
            direct = node.get(manga_id)
            if isinstance(direct, dict):
                return direct

            if str(node.get('manga_id', '')) == manga_id:
                return node

            for value in node.values():
                found = self._find_manga_in_catalog(value, manga_id)
                if found is not None:
                    return found

        if isinstance(node, list):
            for item in node:
                found = self._find_manga_in_catalog(item, manga_id)
                if found is not None:
                    return found

        return None

    def _get_manga_from_api_index(self, manga_id: str):
        data = self._get_catalog_data()
        found = self._find_manga_in_catalog(data, manga_id)
        if found is not None:
            return found

        # Se não achou, força refresh uma vez e tenta novamente.
        data = self._get_catalog_data(force_refresh=True)
        found = self._find_manga_in_catalog(data, manga_id)
        if found is not None:
            return found

        print(f"[Manhastro] manga_id {manga_id} não encontrado em /dados")
        return None

    def _get_manga_title_by_id(self, manga_id: str) -> str | None:
        try:
            manga = self._get_manga_from_api_index(manga_id)
            if not manga:
                return None
            return (
                manga.get('titulo_brasil')
                or manga.get('titulo')
                or None
            )
        except Exception:
            return None

    def login(self, force=False):
        if not force and self.access_token:
            return True

        turnstile_token = os.getenv('MANHASTRO_TURNSTILE_TOKEN', self.turnstile_token)
        files = {
            'email': (None, self.login_email),
            'password': (None, self.login_password),
            'extended_session': (None, 'true'),
            'turnstile_token': (None, turnstile_token)
        }

        try:
            response = requests.post(
                f'{self.api_base}/user/login',
                headers={'accept': 'application/json'},
                files=files,
                timeout=self.timeout
            )
            payload = response.json()
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {'data': payload}

            token = None
            if isinstance(payload, dict):
                data = payload.get('data')
                if isinstance(data, dict):
                    token = data.get('token')
                elif isinstance(data, str):
                    # Alguns retornos trazem data como string JSON ou token puro.
                    try:
                        parsed_data = json.loads(data)
                        if isinstance(parsed_data, dict):
                            token = parsed_data.get('token')
                        elif isinstance(parsed_data, str):
                            token = parsed_data
                    except json.JSONDecodeError:
                        token = data
                if not token and isinstance(payload.get('token'), str):
                    token = payload.get('token')

            if response.status_code in [200, 201] and token:
                self._save_token(token)
                return True
            print(f"[Manhastro] Falha no login: {response.status_code} - {payload}")
            return False
        except Exception as e:
            print(f"[Manhastro] Erro no login: {e}")
            return False

    def getManga(self, link: str) -> Manga:
        manga_id = self._extract_manga_id(link)
        title = None

        if manga_id:
            title = self._get_manga_title_by_id(manga_id)

        if not title:
            response = requests.get(link, timeout=self.timeout)
            soup = BeautifulSoup(response.text, 'html.parser')
            title = self._extract_title(soup)
            if not manga_id:
                placeholder = soup.select_one(self.query_placeholder)
                if placeholder:
                    manga_id = placeholder.get('data-id')

        if not manga_id:
            manga_id = link

        return Manga(id=str(manga_id), name=title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        try:
            if not self.access_token and not self.login():
                return []

            manga_id = self._extract_manga_id(str(id))
            if not manga_id:
                return []

            title = self._get_manga_title_by_id(manga_id) or f'Manga {manga_id}'

            response = requests.get(
                f'{self.api_base}/dados/{manga_id}',
                headers=self._auth_headers(),
                timeout=self.timeout
            )

            if response.status_code in [401, 403] and self.login(force=True):
                response = requests.get(
                    f'{self.api_base}/dados/{manga_id}',
                    headers=self._auth_headers(),
                    timeout=self.timeout
                )

            payload = response.json()
            data = payload.get('data', []) if isinstance(payload, dict) else []
            chs = []
            for chapter in data:
                capitulo_id = chapter.get('capitulo_id')
                capitulo_nome = chapter.get('capitulo_nome') or f'Capitulo {capitulo_id}'
                if capitulo_id is None:
                    continue
                chs.append(Chapter(str(capitulo_id), capitulo_nome, title))
            return chs
        except Exception as e:
            print(f"Erro ao obter capítulos: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        try:
            if not self.access_token and not self.login():
                return Pages(ch.id, ch.number, ch.name, [])

            chapter_id = self._extract_manga_id(str(ch.id))
            if not chapter_id:
                return Pages(ch.id, ch.number, ch.name, [])

            response = requests.get(
                f'{self.api_base}/paginas/{chapter_id}',
                headers=self._auth_headers(),
                timeout=self.timeout
            )

            if response.status_code in [401, 403] and self.login(force=True):
                response = requests.get(
                    f'{self.api_base}/paginas/{chapter_id}',
                    headers=self._auth_headers(),
                    timeout=self.timeout
                )

            raw = response.text.strip()
            if raw.startswith('_'):
                raw = raw[1:]
            payload = json.loads(raw) if raw else {}
            data = payload.get('data', {}) if isinstance(payload, dict) else {}
            pages_list = []

            if isinstance(data, dict) and isinstance(data.get('chapter'), dict):
                chapter_data = data.get('chapter', {})
                base_url = str(chapter_data.get('baseUrl', '')).strip()
                chapter_hash = str(chapter_data.get('hash', '')).strip('/')
                files = chapter_data.get('data', [])

                if base_url.startswith('//'):
                    base_url = f'https:{base_url}'
                if base_url.startswith('/'):
                    base_url = urljoin(self.url, base_url)

                if isinstance(files, list):
                    for file_name in files:
                        if not file_name:
                            continue
                        normalized_name = str(file_name).lstrip('/')
                        src = f"{base_url.rstrip('/')}/{chapter_hash}/{normalized_name}"
                        pages_list.append(src)

            # Fallback para formato legado já tratado anteriormente.
            if not pages_list:
                paginas = data.get('paginas', {}) if isinstance(data, dict) else {}
                for key in sorted(paginas.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
                    src = paginas.get(key)
                    if not src:
                        continue
                    if src.startswith('//'):
                        src = f'https:{src}'
                    elif src.startswith('/'):
                        src = urljoin(self.url, src)
                    pages_list.append(src)

            number_match = re.findall(r'\d+\.?\d*', str(ch.number))
            number = number_match[0] if number_match else str(ch.number)
            return Pages(ch.id, number, ch.name, pages_list)
        except Exception as e:
            print(f"Erro ao obter páginas: {e}")
            return Pages(ch.id, ch.number, ch.name, [])
    
    def adjust_template_size(self, template, img):
        try:
            if template is None or img is None:
                return None
                
            h_img, w_img = img.shape[:2]
            h_template, w_template = template.shape[:2]
            
            if h_template <= 0 or w_template <= 0 or h_img <= 0 or w_img <= 0:
                return None

            if h_template > h_img or w_template > w_img:
                scale_h = h_img / h_template
                scale_w = w_img / w_template
                scale = min(scale_h, scale_w)
                
                new_width = max(1, int(w_template * scale))
                new_height = max(1, int(h_template * scale))
                
                template = cv2.resize(template, (new_width, new_height))
                
                if template is None or template.shape[0] == 0 or template.shape[1] == 0:
                    return None

            return template
        
        except Exception as e:
            print(f"❌ Erro ao ajustar tamanho do template: {e}")
            return None
    
    def removeMark(self, img_path, template_path, output_path) -> bool:
        try:
            if not os.path.exists(img_path):
                print(f"❌ Imagem não encontrada: {img_path}")
                return False
                
            if not os.path.exists(template_path):
                print(f"❌ Template não encontrado: {template_path}")
                return False
            
            try:
                import numpy as np
                with open(img_path, 'rb') as f:
                    file_bytes = np.asarray(bytearray(f.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"❌ Erro ao carregar imagem com numpy: {e}")
                img = cv2.imread(img_path)
            
            if img is None:
                print(f"❌ Erro ao carregar imagem: {img_path}")
                return False
            
            try:
                import numpy as np
                with open(template_path, 'rb') as f:
                    template_bytes = np.asarray(bytearray(f.read()), dtype=np.uint8)
                template = cv2.imdecode(template_bytes, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"❌ Erro ao carregar template com numpy: {e}")
                template = cv2.imread(template_path)
            
            if template is None:
                print(f"❌ Erro ao carregar template: {template_path}")
                return False
            
            if img.shape[0] == 0 or img.shape[1] == 0:
                print(f"❌ Imagem com dimensões inválidas: {img_path}")
                return False
                
            if template.shape[0] == 0 or template.shape[1] == 0:
                print(f"❌ Template com dimensões inválidas: {template_path}")
                return False
            
            template = self.adjust_template_size(template, img)
            
            if template is None or template.shape[0] == 0 or template.shape[1] == 0:
                print(f"❌ Template inválido após redimensionamento")
                return False

            h, w = template.shape[:2]
            
            if img.shape[0] < h or img.shape[1] < w:
                print(f"❌ Imagem muito pequena para o template. Img: {img.shape[:2]}, Template: {h}x{w}")
                return False

            img_cropped = img[-h:, :]

            # Template matching
            result = cv2.matchTemplate(img_cropped, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= 0.8:
                img_without_mark = img[:-h, :]
                
                try:
                    is_success, buffer = cv2.imencode(".jpg", img_without_mark)
                    if is_success:
                        with open(output_path, 'wb') as f:
                            f.write(buffer)
                        print(f"✅ Marca d'água removida: {os.path.basename(output_path)}")
                        return True
                    else:
                        print(f"❌ Erro ao codificar imagem processada")
                        return False
                except Exception as e:
                    print(f"❌ Erro ao salvar imagem processada: {e}")
                    return False
            # else:
            #    print(f"⚠️ Marca d'água não detectada (confiança: {max_val:.2%})")
            
            return False
            
        except Exception as e:
            print(f"❌ Erro no processamento de marca d'água: {e}")
            print(f"   Imagem: {img_path}")
            print(f"   Template: {template_path}")
            return False
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        print(f"tipo:{type(fn)}")
        print(f"fn:{fn}")
        pages = DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)
        marks = ['mark.jpg', 'mark2.jpg', 'mark3.jpg', 'mark4.jpg', 'mark5.jpg', 'mark6.jpg', 'mark7.jpg', 'mark8.jpg', 'mark9.jpg', 'mark10.jpg', 'mark11.jpg', 'mark12.jpg', 'mark13.jpg', 'mark14.jpg', 'mark15.jpg']
        temp_page = sorted(pages.files)
        for page in temp_page[-2:]:
            print(f'Removendo marca d\'água de: {page}')
            for mark in marks:
                if self.removeMark(page, os.path.join(Path(__file__).parent, mark), page):
                    break
        return  pages
