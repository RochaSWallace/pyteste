import os
import re
import base64
import math
import pillow_avif
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from PIL import Image, UnidentifiedImageError
from core.__seedwork.infra.http import Http
from core.config.img_conf import get_config
from core.download.domain.dowload_entity import Chapter as DChapter
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from core.providers.infra.template.scan_madara_clone import ScanMadaraClone
from core.config.login_data import insert_login, LoginData, get_login
from time import sleep

class RfDragonScanProvider(ScanMadaraClone):
    name = 'Rf Dragon Scan'
    lang = 'pt-Br'
    domain = ['rfdragonscan.com']
    has_login = True

    def __init__(self):
        self.url = 'https://rfdragonscan.com'
        self.domain_name = 'rfdragonscan.com'
        self.login_url = f'{self.url}/accounts/login/'

    def _extract_cookies(self, cookies) -> dict:
        cookies_dict = {}

        for cookie in cookies:
            if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                cookies_dict[cookie.name] = cookie.value
            elif isinstance(cookie, dict):
                name = cookie.get('name')
                value = cookie.get('value')
                if name and value:
                    cookies_dict[name] = value

        return cookies_dict

    def _is_svg_content(self, content: bytes) -> bool:
        head = content[:512].lstrip()
        if not head:
            return False
        return head.startswith(b'<?xml') or head.startswith(b'<svg') or b'<svg' in head

    def _save_svg_as_jpg(self, content: bytes, file_path: str) -> bool:
        try:
            decoded = content.decode('utf-8', errors='ignore')
            match = re.search(r'(?:xlink:href|href)\s*=\s*"data:image\/[^;]+;base64,([^"]+)"', decoded)
            if not match:
                print('[RfDragonScan] SVG sem imagem embutida em base64')
                return False

            image_bytes = base64.b64decode(match.group(1))
            img = Image.open(BytesIO(image_bytes))

            if img.mode in ('RGBA', 'LA'):
                alpha_channel = img.getchannel('A') if 'A' in img.getbands() else None
                background = Image.new('RGB', img.size, (255, 255, 255))
                if alpha_channel is not None:
                    background.paste(img, mask=alpha_channel)
                else:
                    background.paste(img)
                img = background
            elif img.mode == 'P':
                img = img.convert('RGBA')
                alpha_channel = img.getchannel('A') if 'A' in img.getbands() else None
                background = Image.new('RGB', img.size, (255, 255, 255))
                if alpha_channel is not None:
                    background.paste(img, mask=alpha_channel)
                else:
                    background.paste(img)
                img = background
            else:
                img = img.convert('RGB')

            img.save(file_path, quality=90, dpi=(72, 72))
            return True
        except (UnidentifiedImageError, OSError, ValueError, TypeError, RuntimeError) as e:
            print(f'[RfDragonScan] Falha ao converter SVG para JPG: {e}')
            return False

    def login(self):
        login_info = get_login(self.domain_name)
        if login_info:
            print('[RfDragonScan] Login encontrado em cache')
            return True

        print('[RfDragonScan] Iniciando navegador para login...')
        print('[RfDragonScan] Voce tem 45 segundos para concluir o login manual')

        try:
            from DrissionPage import ChromiumPage, ChromiumOptions

            co = ChromiumOptions()
            co.headless(False)

            page = ChromiumPage(addr_or_opts=co)
            page.get(self.login_url)

            print(f'[RfDragonScan] Aguardando em: {self.login_url}')
            sleep(45)

            cookies_dict = self._extract_cookies(page.cookies())
            page.quit()

            if not cookies_dict:
                print('[RfDragonScan] Nenhum cookie foi capturado')
                return False

            insert_login(LoginData(self.domain_name, {}, cookies_dict))
            print(f'[RfDragonScan] Login salvo com sucesso ({len(cookies_dict)} cookies)')
            return True
        except ImportError:
            print('[RfDragonScan] DrissionPage nao esta instalado. Execute: pip install DrissionPage')
            return False
        except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError) as e:
            print(f'[RfDragonScan] Erro durante login: {e}')
            return False

    def download(self, pages, fn: any, headers=None, cookies=None):
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path,
                            str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)

        img_format = config.img
        files = []
        page_number = 0

        for i, page in enumerate(pages.pages):
            request_headers = {'referer': f'{self.url}'}
            if headers is not None:
                request_headers = {**headers, **request_headers}

            response = Http.get(page, headers=request_headers, cookies=cookies)
            zip_content = BytesIO(response.content)

            with ZipFile(zip_content) as zip_file:
                for file_name in zip_file.namelist():
                    print(f'[RfDragonScan] Processando arquivo: {file_name}')
                    base_name = os.path.basename(file_name)
                    if not base_name:
                        continue

                    file_ext = os.path.splitext(base_name)[1].lower()

                    with zip_file.open(file_name) as file_in_zip:
                        content = file_in_zip.read()

                    # O site envia SVG com extensao .s em varios capitulos.
                    if file_ext == '.s' and self._is_svg_content(content):
                        page_number += 1
                        file_path = os.path.join(path, f'{page_number:03d}.jpg')
                        if self._save_svg_as_jpg(content, file_path):
                            files.append(file_path)
                        else:
                            fallback_path = os.path.join(path, f'{page_number:03d}.svg')
                            files.append(fallback_path)
                            Path(fallback_path).write_bytes(content)
                        continue

                    if file_ext == '.s':
                        continue

                    page_number += 1

                    if file_ext == '.svg':
                        file_path = os.path.join(path, f'{page_number:03d}.jpg')
                        if self._save_svg_as_jpg(content, file_path):
                            files.append(file_path)
                        else:
                            fallback_path = os.path.join(path, f'{page_number:03d}.svg')
                            files.append(fallback_path)
                            Path(fallback_path).write_bytes(content)
                        continue

                    try:
                        img = Image.open(BytesIO(content))
                        img.verify()

                        img = Image.open(BytesIO(content))
                        icc = img.info.get('icc_profile')
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')

                        file_path = os.path.join(path, f'%03d{img_format}' % page_number)
                        files.append(file_path)
                        img.save(file_path, quality=80, dpi=(72, 72), icc_profile=icc)
                    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
                        fallback_ext = file_ext if file_ext else img_format
                        if not fallback_ext.startswith('.'):
                            fallback_ext = f'.{fallback_ext}'
                        file_path = os.path.join(path, f'{page_number:03d}{fallback_ext}')
                        files.append(file_path)
                        Path(file_path).write_bytes(content)

            if fn is not None:
                fn(math.ceil(i * 100) / len(pages.pages))

        if fn is not None:
            fn(math.ceil(len(pages.pages) * 100) / len(pages.pages))

        return DChapter(pages.number, files)