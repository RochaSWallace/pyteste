from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
import os
import math
import requests
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.domain.dowload_entity import Chapter as DownloadedChapter
from core.config.img_conf import get_config
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from PIL import Image
from io import BytesIO
import concurrent.futures
from threading import Lock
import re

class PlumaComicsProvider(WordpressEtoshoreMangaTheme):
    name = 'Pluma Comics'
    lang = 'pt_Br'
    domain = ['plumacomics.cloud']

    def __init__(self) -> None:
        self.url = 'https://plumacomics.cloud'
        self.link = 'https://plumacomics.cloud'
        self.get_title = 'h1'
        self.get_chapters_list = 'div.space-y-1'
        self.chapter = 'a[href^="/ler/"]'
        self.get_chapter_number = 'span.text-sm'
        self.get_div_page = 'div#chapter-pages'
        self.get_pages = 'img[src]'

    def getManga(self, link: str) -> Manga:
        response = link.replace(f"{self.url}/series/", "").replace("-", " ")

        title = response.title()
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        chapters_list = soup.select_one(self.get_chapters_list)
        
        if not chapters_list:
            return []
        
        chapter_links = chapters_list.select(self.chapter)
        title = id.replace(f"{self.url}/series/", "").replace("-", " ").title()
        chapters = []
        
        for ch in chapter_links:
            href = ch.get('href')
            if not href:
                continue
            
            # Monta URL completa se for relativa
            if href.startswith('/'):
                href = self.url + href
            
            # Extrai o número do capítulo
            number_span = ch.select_one(self.get_chapter_number)
            if number_span:
                # Extrai apenas números (com suporte a decimais)
                text = number_span.get_text(strip=True)
                match = re.search(r'(\d+(?:\.\d+)?)', text)
                number = match.group(1) if match else str(len(chapters) + 1)
            else:
                # Fallback: tenta extrair do href (/ler/XXXX)
                match = re.search(r'/ler/(\d+)', href)
                number = match.group(1) if match else str(len(chapters) + 1)
            
            chapters.append(Chapter(href, number, title))
        
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Busca o container de páginas
        div_pages = soup.select_one(self.get_div_page)
        
        if not div_pages:
            return Pages(ch.id, ch.number, ch.name, [])
        
        # Busca todas as imagens
        images = div_pages.select(self.get_pages)
        img_urls = []
        
        for img in images:
            src = img.get('src')
            if not src:
                continue
            
            # Converte URLs relativas para absolutas
            if src.startswith('/'):
                src = self.url + src
            
            img_urls.append(src)
        
        return Pages(ch.id, ch.number, ch.name, img_urls)

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        """
        Download customizado para URLs temporárias (/api/read/...?...).
        Baixa as imagens em paralelo para reduzir expiração de token.
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        total_pages = len(pages.pages)
        if total_pages == 0:
            return DownloadedChapter(pages.number, [])

        files = [None] * total_pages
        progress_lock = Lock()
        completed = 0

        if fn is not None:
            fn(0)

        def baixar_img(idx_img_url):
            nonlocal completed
            idx, img_url = idx_img_url
            try:
                download_headers = {
                    'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'accept-language': 'pt-BR,pt;q=0.5',
                    'priority': 'i',
                    'sec-ch-ua': '"Not:A-Brand";v="99", "Brave";v="145", "Chromium";v="145"',
                    'sec-ch-ua-arch': '""',
                    'sec-ch-ua-bitness': '"64"',
                    'sec-ch-ua-full-version-list': '"Not:A-Brand";v="99.0.0.0", "Brave";v="145.0.0.0", "Chromium";v="145.0.0.0"',
                    'sec-ch-ua-mobile': '?1',
                    'sec-ch-ua-model': '"Nexus 5"',
                    'sec-ch-ua-platform': '"Android"',
                    'sec-ch-ua-platform-version': '"6.0"',
                    'referer': pages.id,
                    'sec-fetch-dest': 'image',
                    'sec-fetch-mode': 'no-cors',
                    'sec-fetch-site': 'same-origin',
                    'sec-gpc': '1',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                if headers:
                    download_headers = {**download_headers, **headers}

                response = requests.get(img_url, headers=download_headers, cookies=cookies, timeout=30)
                response.raise_for_status()

                img = Image.open(BytesIO(response.content))
                icc = img.info.get('icc_profile')
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                file_path = os.path.join(path, f"%03d{img_format}" % (idx + 1))
                img.save(file_path, quality=100, dpi=(72, 72), icc_profile=icc)

                if fn is not None:
                    with progress_lock:
                        completed += 1
                        fn(math.ceil((completed * 100) / total_pages))

                return idx, file_path
            except Exception as e:
                print(f"[PlumaComics] ✗ Erro na imagem {idx+1}: {str(e)[:120]}")
                return idx, None

        max_workers = min(8, total_pages)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(baixar_img, enumerate(pages.pages)))

        falhas = 0
        for idx, file_path in results:
            if file_path:
                files[idx] = file_path
            else:
                falhas += 1

        files = [f for f in files if f]

        if falhas > 0:
            raise Exception(f"Falha ao baixar {falhas} de {total_pages} páginas do capítulo")

        if fn is not None:
            fn(100)

        return DownloadedChapter(pages.number, files)
