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
        Usa requisição HTTP para obter o HTML e extrai as imagens.
        """
        uri = urljoin(self.url, ch.id)
        
        try:
            urls_imagens = self._get_images_http(uri)
            if urls_imagens:
                number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
                return Pages(ch.id, number, ch.name, urls_imagens)
        except Exception as e:
            print(f"[HuntersScan] Falha ao extrair imagens: {e}")
        
        raise Exception(f"Não foi possível extrair as URLs das imagens do capítulo: {ch.id}")
    
    def _get_images_http(self, url_capitulo):
        """
        Usa requisição HTTP direta para obter o HTML e BeautifulSoup para extrair os links das imagens.
        """
        try:
            page_headers = {
                **self.headers,
                'Referer': url_capitulo,
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': '*/*'
            }
            
            response = Http.get(
                url_capitulo, 
                headers=page_headers,
                timeout=self.timeout
            )
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar as imagens usando a query configurada
            imagens = soup.select(self.query_pages_img)
            
            if not imagens:
                # Tentar seletor alternativo
                imagens = soup.select('div.reading-content img')
            
            if not imagens:
                print(f"[HuntersScan] Nenhuma imagem encontrada")
                return []
            
            urls_imagens = []
            for img in imagens:
                src = img.get('src', '').strip()
                data_src = img.get('data-src', '').strip()
                data_lazy_src = img.get('data-lazy-src', '').strip()
                
                url = src or data_src or data_lazy_src
                
                if url and (url.startswith('http://') or url.startswith('https://')):
                    url = url.strip()
                    urls_imagens.append(url)
            
            if not urls_imagens:
                print("[HuntersScan] Nenhuma URL de imagem válida foi extraída.")
                return []
            
            # Ordenar as URLs pelo número no nome do arquivo
            def extrair_numero(url):
                try:
                    nome_arquivo = url.split('/')[-1]
                    numero = nome_arquivo.split('.')[0]
                    # Tenta extrair apenas dígitos do nome
                    digits = ''.join(filter(str.isdigit, numero))
                    return int(digits) if digits else 0
                except (ValueError, IndexError):
                    return 0
            
            urls_ordenadas = sorted(urls_imagens, key=extrair_numero)
            
            print(f"[HuntersScan] Total de {len(urls_ordenadas)} imagens extraídas.")
            return urls_ordenadas
            
        except Exception as e:
            print(f"[HuntersScan] Erro ao extrair URLs via HTTP: {e}")
            return []
    
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