from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
import os
import math
import requests
import re
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
import concurrent.futures


class AstraToonsProvider(WordpressEtoshoreMangaTheme):
    name = 'Astra Toons'
    lang = 'pt_Br'
    domain = ['new.astratoons.com', 'astratoons.com']


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
       
        # Obter o título do mangá e o comic_id da página principal
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
       
        # Buscar título do mangá
        title_element = soup.select_one(self.get_title)
        manga_title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
       
        # Extrair comic_id do HTML
        comic_id = None
        
        # Procurar em elementos com Alpine.js (x-data) por comicId
        for tag in soup.find_all(attrs={'x-data': True}):
            x_data = tag.get('x-data', '')
            match = re.search(r'comicId:\s*(\d+)', x_data)
            if match:
                comic_id = match.group(1)
                print(f"[AstraToons] 🔍 Comic ID encontrado via x-data: {comic_id}")
                break
        
        # Fallback: Procurar em scripts por comicId
        if not comic_id:
            for script in soup.find_all('script'):
                if script.string:
                    match = re.search(r'comicId:\s*(\d+)', script.string)
                    if match:
                        comic_id = match.group(1)
                        print(f"[AstraToons] 🔍 Comic ID encontrado em script: {comic_id}")
                        break
        
        if not comic_id:
            print(f"[AstraToons] ⚠️ Não foi possível encontrar comic_id")
            return list
       
        print(f"[AstraToons] 🔍 Comic ID: {comic_id}")
       
        # Fazer requisições paginadas para a API
        page = 1
        has_more = True
        
        while has_more:
            try:
                api_url = f"{self.url}/api/comics/{comic_id}/chapters?search=&order=desc&page={page}"
                
                api_response = requests.get(api_url, headers={
                    'accept': '*/*',
                    'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                    'referer': id,
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                
                api_response.raise_for_status()
                data = api_response.json()
                
                html_content = data.get('html', '')
                has_more = data.get('hasMore', False)
                
                # Parse o HTML retornado
                chapter_soup = BeautifulSoup(html_content, 'html.parser')
                chapter_links = chapter_soup.select('a[href*="/capitulo/"]')
                
                print(f"[AstraToons] 📄 Página {page}: {len(chapter_links)} capítulos")
                
                for ch_link in chapter_links:
                    chapter_url = ch_link.get('href')
                    
                    if not chapter_url:
                        continue
                    
                    # Extrair nome do capítulo
                    chapter_text_elem = ch_link.select_one('span.text-lg')
                    
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
                
                page += 1
                
                # Proteção contra loop infinito
                if page > 100:
                    print(f"[AstraToons] ⚠️ Limite de 100 páginas atingido")
                    break
                    
            except Exception as e:
                print(f"[AstraToons] ❌ Erro na página {page}: {e}")
                break
       
        print(f"[AstraToons] ✅ Total: {len(list)} capítulos")
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
        Download das URLs interceptadas de /proxy/image/ em paralelo.
        """
        
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        files = [None] * len(pages.pages)
        total_pages = len(pages.pages)

        def baixar_img(idx_img_url):
            idx, img_url = idx_img_url
            try:
                download_headers = {
                    'accept': '*/*',
                    'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                    'referer': pages.id,
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                print(f"[AstraToons] ↓ Baixando imagem {idx+1}/{total_pages}: {img_url}")
                response = requests.get(img_url, headers=download_headers, timeout=30)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                file_path = os.path.join(path, f"%03d{img_format}" % (idx+1))
                img.save(file_path, quality=100, dpi=(72, 72))
                if fn is not None:
                    fn(math.ceil((idx+1) * 100) / total_pages)
                return idx, file_path
            except Exception as e:
                print(f"[AstraToons] ✗ Erro na imagem {idx+1}: {str(e)[:60]}")
                return idx, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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
        return DownloadedChapter(pages.number, files)