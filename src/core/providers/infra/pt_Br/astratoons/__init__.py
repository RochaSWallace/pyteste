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
import nodriver as uc
import asyncio


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
        """
        Obtém páginas interceptando requisições de rede via CDP.
        
        O site faz fetch de URLs como /proxy/image/?expires=...&signature=...
        antes de converter para blob. Interceptamos essas requisições para
        capturar as URLs reais.
        """
        async def _get_pages_async():
            intercepted_urls = []
            
            try:
                # Configura nodriver para VPS/root
                config = uc.Config(
                    headless=True,
                    sandbox=False,
                    browser_args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                )
                
                browser = await uc.start(config)
                page = await browser.get(ch.id)
                
                # Habilita interceptação de rede via CDP
                await page.send(uc.cdp.network.enable())
                
                # Handler para capturar requisições
                def request_handler(event):
                    if isinstance(event, uc.cdp.network.RequestWillBeSent):
                        url = event.request.url
                        # Captura URLs de imagens do proxy
                        if '/proxy/image/' in url:
                            intercepted_urls.append(url)
                
                # Registra handler
                page.add_handler(uc.cdp.network.RequestWillBeSent, request_handler)
                
                # Aguarda carregamento das imagens
                await asyncio.sleep(5)
                
                # Remove handler
                page.remove_handler(uc.cdp.network.RequestWillBeSent, request_handler)
                
                print(f"[AstraToons] ✅ Encontradas {len(intercepted_urls)} imagens")
                
                # Fecha browser
                try:
                    await browser.stop()
                except:
                    pass
                
                return intercepted_urls
            
            except Exception as e:
                print(f"[AstraToons] ❌ Erro ao obter páginas: {e}")
                import traceback
                traceback.print_exc()
                try:
                    if 'browser' in locals() and browser:
                        await browser.stop()
                except:
                    pass
                return []
        
        img_urls = asyncio.run(_get_pages_async())
        return Pages(ch.id, ch.number, ch.name, img_urls)

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        """
        Download das URLs interceptadas de /proxy/image/
        
        As URLs já vêm prontas do getPages via interceptação de rede.
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        files = []
        total_pages = len(pages.pages)
        
        for idx, img_url in enumerate(pages.pages, start=1):
            try:
                # Headers para imitar o navegador
                download_headers = {
                    'accept': '*/*',
                    'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                    'referer': pages.id,  # URL do capítulo
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.get(img_url, headers=download_headers, timeout=30)
                response.raise_for_status()
                
                # Abre e salva imagem
                img = Image.open(BytesIO(response.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                file_path = os.path.join(path, f"%03d{img_format}" % idx)
                img.save(file_path, quality=100, dpi=(72, 72))
                files.append(file_path)
                
                if fn is not None:
                    fn(math.ceil(idx * 100) / total_pages)
                    
            except Exception as e:
                print(f"[AstraToons] ✗ Erro na imagem {idx}: {str(e)[:60]}")
                continue
        
        return DownloadedChapter(pages.number, files)