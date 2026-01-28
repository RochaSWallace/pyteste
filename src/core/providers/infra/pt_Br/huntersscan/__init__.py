import re
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List
from DrissionPage import ChromiumPage, ChromiumOptions
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Pages
from core.download.application.use_cases import DownloadUseCase
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.config.login_data import insert_login, LoginData, get_login, delete_login

class HuntersScanProvider(WordPressMadara):
    name = 'Hunters scan'
    lang = 'pt-Br'
    domain = ['readhunters.xyz']
    has_login = True

    def __init__(self):
        self.url = 'https://readhunters.xyz'
        self.domain_name = 'readhunters.xyz'
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_pages_img = 'div.reading-content img.wp-manga-chapter-img'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.headers = {
            'Referer': f'{self.url}/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        self.timeout = 10
    
    def _is_logged_in(self, html) -> bool:
        """Verifica se está logado analisando o HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        user_menu = soup.select_one('.c-user_menu, .user-menu, .logged-in')
        login_link = soup.select_one('a[href*="login"], a.login')
        
        if not login_link and user_menu:
            return True
        
        if login_link:
            return False
            
        return False
    
    def login(self):
        """Realiza login usando DrissionPage para capturar cookies do navegador real"""
        login_info = get_login(self.domain_name)
        if login_info:
            print("[HuntersScan] ✅ Login encontrado em cache")
            return True
        
        print("[HuntersScan] 🔐 Iniciando navegador para login...")
        print("[HuntersScan] 📝 Você tem 30 segundos para fazer login")
        
        try:
            co = ChromiumOptions()
            co.headless(False)
            
            page = ChromiumPage(addr_or_opts=co)
            page.get(f'{self.url}/')
            
            print("[HuntersScan] ⏳ Aguardando 30 segundos...")
            sleep(30)
            
            print("[HuntersScan] ✅ Capturando cookies...")
            
            cookies = page.cookies()
            cookies_dict = {}
            
            for cookie in cookies:
                if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                    cookies_dict[cookie.name] = cookie.value
                elif isinstance(cookie, dict):
                    cookies_dict[cookie.get('name')] = cookie.get('value')
            
            print(f"[HuntersScan] 🍪 {len(cookies_dict)} cookies capturados")
            
            page.quit()
            
            if cookies_dict:
                insert_login(LoginData(self.domain_name, {}, cookies_dict))
                print("[HuntersScan] ✅ Login salvo com sucesso!")
                return True
            else:
                print("[HuntersScan] ❌ Nenhum cookie capturado")
                return False
                
        except ImportError:
            print("[HuntersScan] ❌ DrissionPage não está instalado")
            print("[HuntersScan] Execute: pip install DrissionPage")
            return False
        except Exception as e:
            print(f"[HuntersScan] ❌ Erro durante login: {e}")
            return False
    
    def getManga(self, link: str) -> Manga:
        """Obtém informações do mangá a partir do link"""
        response = Http.get(link, headers=self.headers, timeout=self.timeout)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        return Manga(id=link, name=title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, headers=self.headers, timeout=self.timeout)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        
        # Usa o endpoint AJAX para obter os capítulos
        try:
            data = self._get_chapters_ajax(id)
        except Exception:
            # Fallback: tenta obter do HTML direto
            dom = soup.select('body')[0]
            data = dom.select(self.query_chapters)

        chs = []
        for el in data:
            ch_id = self.get_root_relative_or_absolute_link(el, uri)
            ch_number = el.text.strip()
            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs
    
    def getPages(self, ch: Chapter) -> Pages:
        """
        Extrai URLs das imagens do capítulo.
        O site usa proteção WASM - as imagens são criptografadas no payload JS.
        Usamos DrissionPage para renderizar a página e capturar as URLs após descriptografia.
        """
        uri = urljoin(self.url, ch.id)
        
        print(f"[HuntersScan] 🔄 Carregando capítulo com navegador (proteção WASM)...")
        
        urls_imagens = []
        
        try:
            co = ChromiumOptions()
            #co.headless(True)
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-javascript')
            page = ChromiumPage(addr_or_opts=co)
            page.get(uri)
            
            # Aguardar o JavaScript carregar e descriptografar as imagens
            print(f"[HuntersScan] ⏳ Aguardando renderização das imagens...")
            sleep(60)  # Aguardar WASM processar
            
            # Método 1: Buscar divs com data-src após renderização
            canvas_wraps = page.eles('css:div.js-canvas-wrap[data-src]')
            for div in canvas_wraps:
                data_src = div.attr('data-src')
                if data_src and data_src.strip():
                    urls_imagens.append(data_src.strip())
            
            # Método 2: Se não encontrou, tentar extrair do JavaScript _HuntersOpts
            if not urls_imagens:
                try:
                    # Executar JS para pegar as URLs já processadas
                    result = page.run_js('return window._HuntersOpts ? window._HuntersOpts.imgs : []')
                    if result and isinstance(result, list):
                        urls_imagens = [url for url in result if url]
                except Exception as e:
                    print(f"[HuntersScan] ⚠️ Erro ao extrair imgs do JS: {e}")
            
            # Método 3: Buscar imagens renderizadas no container
            if not urls_imagens:
                imgs = page.eles('css:.reading-content img[src]')
                for img in imgs:
                    src = img.attr('src')
                    if src and 'data:' not in src:
                        urls_imagens.append(src)
            
            # Método 4: Buscar qualquer img com src de imagem
            if not urls_imagens:
                imgs = page.eles('css:img[src*="wp-content/uploads"]')
                for img in imgs:
                    src = img.attr('src')
                    if src:
                        urls_imagens.append(src)
            
            page.quit()
            
        except Exception as e:
            print(f"[HuntersScan] ❌ Erro ao usar navegador: {e}")
            print(f"[HuntersScan] 🔄 Tentando fallback com HTTP...")
            
            # Fallback: tentar método HTTP tradicional
            response = Http.get(uri, timeout=self.timeout)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Tentar extrair URLs do payload JS (base64)
            import base64
            import json
            
            script_text = soup.find('script', string=re.compile(r'_HuntersOpts'))
            if script_text:
                match = re.search(r'payload:\s*"([^"]+)"', script_text.string)
                if match:
                    print(f"[HuntersScan] 📦 Payload encontrado (criptografado)")
            
            # Buscar método padrão
            data = soup.select(self.query_pages)
            for el in data:
                url = self._process_page_element(el, uri)
                if url:
                    urls_imagens.append(url)
        
        if not urls_imagens:
            raise Exception(f"Não foi possível extrair as URLs das imagens do capítulo: {ch.id}. O site usa proteção WASM.")
        
        print(f"[HuntersScan] ✅ {len(urls_imagens)} imagens encontradas")
        
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, urls_imagens)
    
    def _get_chapters_ajax(self, manga_id):
        """Obtém capítulos via POST request para /ajax/chapters/"""
        if not manga_id.endswith('/'):
            manga_id += '/'
        
        ajax_headers = {
            **self.headers,
            'Referer': urljoin(self.url, manga_id),
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': '*/*'
        }
        
        uri = urljoin(self.url, f'{manga_id}ajax/chapters/?t=1')
        response = Http.post(uri, headers=ajax_headers, timeout=self.timeout)
        chapters = self._fetch_dom(response, self.query_chapters)
        
        if chapters:
            return chapters
        else:
            raise Exception('No chapters found (ajax endpoint)!')
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        if headers is not None:
            headers = headers | self.headers
        else:
            headers = self.headers
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies, timeout=self.timeout)