from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
import os
import math
import requests
from PIL import Image
from io import BytesIO
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.domain.dowload_entity import Chapter as DownloadedChapter
from core.config.img_conf import get_config
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name


class AstraToonsProvider(WordpressEtoshoreMangaTheme):
    name = 'Astra Toons'
    lang = 'pt_Br'
    domain = ['new.astratoons.com']

    def __init__(self):
        self.url = 'https://new.astratoons.com'
        self.link = 'https://new.astratoons.com/'
        self.get_title = 'h1'
        self.get_chapters_list = '#chapter-list'
        self.chapter = 'a[href*="/capitulo/"]'
        self.get_chapter_name = 'span.text-lg'
        self.get_div_page = '#reader-container'
        self.get_pages = 'img[src]'

    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_element = soup.select_one(self.get_title)
        title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
            
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        list = []
        
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar título do mangá usando self.get_title
        title_element = soup.select_one(self.get_title)
        manga_title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
        
        # Buscar container de capítulos usando self.get_chapters_list
        chapters_container = soup.select_one(self.get_chapters_list)
        
        if not chapters_container:
            print(f"[AstraToons] Container {self.get_chapters_list} não encontrado")
            return list
        
        # Buscar todos os links de capítulos usando self.chapter
        chapter_links = chapters_container.select(self.chapter)
        
        print(f"[AstraToons] Encontrados {len(chapter_links)} capítulos")
        
        for ch_link in chapter_links:
            chapter_url = ch_link.get('href')
            
            if not chapter_url:
                continue
            
            # Extrair nome do capítulo usando self.get_chapter_name
            chapter_text_elem = ch_link.select_one(self.get_chapter_name)
            
            if chapter_text_elem:
                chapter_name = chapter_text_elem.get_text().strip()
            else:
                # Fallback: extrair do href
                chapter_num = chapter_url.split('/capitulo/')[-1]
                chapter_name = f"Capítulo {chapter_num}"
            
            chapter_obj = Chapter(
                chapter_url if chapter_url.startswith('http') else f"{self.url}{chapter_url}",
                chapter_name,
                manga_title
            )
            list.append(chapter_obj)
        
        return list

    def getPages(self, ch: Chapter) -> Pages:
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar container de imagens usando self.get_div_page
        images_container = soup.select_one(self.get_div_page)
        
        if not images_container:
            print(f"[AstraToons] Container {self.get_div_page} não encontrado")
            return Pages(ch.id, ch.number, ch.name, [])
        
        # Buscar todas as imagens usando self.get_pages
        image_elements = images_container.select(self.get_pages)
        
        if not image_elements:
            print(f"[AstraToons] Nenhuma imagem encontrada com seletor {self.get_pages}")
            return Pages(ch.id, ch.number, ch.name, [])
        
        list = []
        for img in image_elements:
            img_src = img.get('src')
            if img_src:
                # URLs já vêm completas (https://new.astratoons.com/proxy/image/...)
                list.append(img_src)
        
        print(f"[AstraToons] Encontradas {len(list)} páginas")
        return Pages(ch.id, ch.number, ch.name, list)

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        """
        Download customizado que extrai e usa o referrer para imagens protegidas.
        URLs vêm no formato: "REFERRER|URL_DA_IMAGEM"
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        files = []
        total_pages = len(pages.pages)
        
        for idx, page_data in enumerate(pages.pages, start=1):
            try:
                print(f"[AstraToons] [{idx}/{total_pages}] Baixando...")
                
                # Extrai referrer e URL da imagem
                if '|' in page_data:
                    referrer, img_url = page_data.split('|', 1)
                else:
                    # Fallback: sem referrer
                    referrer = pages.id
                    img_url = page_data
                
                # Headers com referrer obrigatório
                download_headers = {
                    "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "accept-language": "pt-BR,pt;q=0.7",
                    "referer": referrer,
                    "sec-ch-ua": '"Brave";v="143", "Chromium";v="143", "Not A(Brand);v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "image",
                    "sec-fetch-mode": "no-cors",
                    "sec-fetch-site": "same-origin",
                    "sec-gpc": "1",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                # Download da imagem
                response = requests.get(img_url, headers=download_headers, timeout=30)
                response.raise_for_status()
                
                # Salva imagem
                img = Image.open(BytesIO(response.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                file_path = os.path.join(path, f"%03d{img_format}" % idx)
                img.save(file_path, quality=100, dpi=(72, 72))
                files.append(file_path)
                
                print(f"  ✓ Salvo: {os.path.basename(file_path)}")
                
                # Progresso
                if fn is not None:
                    fn(math.ceil(idx * 100) / total_pages)
                
            except Exception as e:
                print(f"  ✗ Erro ao baixar página {idx}: {e}")
                continue
        
        print(f"[AstraToons] Download concluído: {len(files)}/{total_pages} imagens")
        return DownloadedChapter(pages.number, files)