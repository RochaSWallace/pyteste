from urllib.parse import urljoin
import re
import time
from typing import List
from fake_useragent import UserAgent
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.application.use_cases import DownloadUseCase
from core.providers.infra.template.wordpress_madara import WordPressMadara
from DrissionPage import ChromiumPage

# Variáveis globais para manter a sessão viva
_GLOBAL_BROWSER = None
_GLOBAL_HEADERS = None
_GLOBAL_COOKIES = None
_LAST_SESSION_TIME = 0
_SESSION_TIMEOUT = 1200  # 20 minutos em segundos

class ImperiodabritanniaProvider(WordPressMadara):
    name = 'Imperio da britannia'
    lang = 'pt-Br'
    domain = ['imperiodabritannia.com']

    def __init__(self):
        self.url = 'https://imperiodabritannia.com/'

        self.path = ''
        
        self.query_mangas = 'div.page-item-detail.manga a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break img'
        self.get_div_page = 'div.reading-content'
        self.get_pages = 'img.wp-manga-chapter-img'
        
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        ua = UserAgent()
        self.user = ua.chrome
        
        # Cache de dados da sessão
        self._headers_cache = None
        self._cookies_cache = None
        
        # Headers base simples (serão atualizados dinamicamente)
        self.base_headers = {
            'User-Agent': self.user,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def _get_browser(self):
        """Retorna o navegador global ou cria um novo se necessário"""
        global _GLOBAL_BROWSER, _LAST_SESSION_TIME
        
        current_time = time.time()
        
        # Verifica se o navegador já existe e está dentro do tempo de timeout
        if _GLOBAL_BROWSER is None or (current_time - _LAST_SESSION_TIME) > _SESSION_TIMEOUT:
            try:
                # Fecha o navegador anterior se existir
                if _GLOBAL_BROWSER:
                    try:
                        _GLOBAL_BROWSER.close()
                    except:
                        pass
                
                # Cria um novo navegador
                _GLOBAL_BROWSER = ChromiumPage()
                _LAST_SESSION_TIME = current_time
                print("[DEBUG] Criando nova instância do navegador")
            except Exception as e:
                print(f"[DEBUG] Erro ao criar navegador: {e}")
                _GLOBAL_BROWSER = None
        else:
            # Atualiza o timestamp da última utilização
            _LAST_SESSION_TIME = current_time
            print("[DEBUG] Reutilizando navegador existente")
            
        return _GLOBAL_BROWSER

    def _capturar_dados_completos(self, url, wait_timeout=20):
        """Captura headers, cookies e outros dados necessários"""
        global _GLOBAL_HEADERS, _GLOBAL_COOKIES
        
        # Verifica se já temos headers e cookies globais válidos
        if _GLOBAL_HEADERS and _GLOBAL_COOKIES:
            print("[DEBUG] Reutilizando headers e cookies globais")
            return _GLOBAL_HEADERS, _GLOBAL_COOKIES
        
        try:
            page = self._get_browser()
            
            # Navegue para a URL apenas se necessário
            current_url = ""
            try:
                current_url = page.url
            except:
                pass
                
            # Se não estiver na URL desejada ou em uma página relacionada, navega para ela
            if not current_url or not (self.url in current_url or url in current_url):
                page.get(url)
                
                # Aguarda até que o HTML não contenha mais a mensagem de challenge
                start = time.time()
                while time.time() - start < wait_timeout:
                    html = ''
                    try:
                        html = page.html
                    except Exception:
                        pass
                    if html and 'Enable JavaScript and cookies to continue' not in html:
                        break
                    time.sleep(1)
                
                # Aguarda carregamento adicional
                time.sleep(2)
            
            # Captura TODOS os cookies
            all_cookies = []
            try:
                all_cookies = page.cookies()
            except Exception:
                try:
                    all_cookies = page.cookies
                except Exception:
                    all_cookies = []
            
            # Se não conseguiu com DrissionPage, tenta via driver
            if not all_cookies and hasattr(page, 'driver'):
                try:
                    all_cookies = page.driver.get_cookies()
                except Exception:
                    all_cookies = []
            
            cookie_str = "; ".join([f"{c.get('name')}={c.get('value')}" 
                                   for c in all_cookies 
                                   if c.get('name') and c.get('value')])
            
            # Captura user-agent real do navegador
            user_agent = self.user
            try:
                user_agent = page.run_js('return navigator.userAgent;')
            except Exception:
                pass
            
            # Atualiza headers com dados reais baseados no curl
            updated_headers = {
                'accept': '*/*',
                'accept-language': 'pt-BR,pt;q=0.8',
                'origin': self.url.rstrip('/'),
                'priority': 'u=1, i',
                'referer': url,
                'sec-ch-ua': '"Not;A=Brand";v="99", "Brave";v="139", "Chromium";v="139"',
                'sec-ch-ua-arch': '"x86"',
                'sec-ch-ua-bitness': '"64"',
                'sec-ch-ua-full-version-list': '"Not;A=Brand";v="99.0.0.0", "Brave";v="139.0.0.0", "Chromium";v="139.0.0.0"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-model': '""',
                'sec-ch-ua-platform': '"Windows"',
                'sec-ch-ua-platform-version': '"19.0.0"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'sec-gpc': '1',
                'user-agent': user_agent,
                'x-requested-with': 'XMLHttpRequest',
                'cookie': cookie_str,
            }
            
            print(f"[DEBUG] Cookies capturados: {cookie_str[:100]}...")
            print(f"[DEBUG] User-Agent: {user_agent}")
            
            # Atualiza as variáveis globais
            _GLOBAL_HEADERS = updated_headers
            _GLOBAL_COOKIES = cookie_str
            
            return updated_headers, cookie_str
            
        except Exception as e:
            print(f"[DEBUG] Erro ao capturar dados: {e}")
            return self.base_headers, None

    def _get_headers(self, url=None, force_refresh=False):
        """Retorna headers cached ou captura novos se necessário"""
        global _GLOBAL_HEADERS, _GLOBAL_COOKIES
        
        if force_refresh or not self._headers_cache:
            target_url = url or self.url
            self._headers_cache, self._cookies_cache = self._capturar_dados_completos(target_url)
            
            # Atualiza também as variáveis globais
            if self._headers_cache and self._cookies_cache:
                _GLOBAL_HEADERS = self._headers_cache
                _GLOBAL_COOKIES = self._cookies_cache
        
        return self._headers_cache

    def _refresh_headers(self, url=None):
        """Força recaptura dos headers"""
        return self._get_headers(url, force_refresh=True)
        
    def _check_response_valid(self, response):
        """Verifica se a resposta é válida ou se precisa atualizar a sessão"""
        if not response:
            return False
            
        # Verifica status code
        if getattr(response, 'status_code', 0) not in range(200, 299):
            return False
            
        # Verifica conteúdo para sinais de desafio CloudFlare ou sessão expirada
        text = getattr(response, 'text', '')
        invalid_markers = [
            'Enable JavaScript and cookies to continue',
            'Checking if the site connection is secure',
            'Please wait while we verify your browser',
            'Challenge Validation'
        ]
        
        for marker in invalid_markers:
            if marker in text:
                return False
                
        return True

    def getManga(self, link: str) -> Manga:
        """Obtém dados do mangá com possibilidade de retry"""
        try:
            # Usa headers cacheados na primeira tentativa
            headers = self._get_headers()
            response = Http.get(link, headers=headers, timeout=getattr(self, 'timeout', None))
            
            # Verifica se a resposta é válida
            if not self._check_response_valid(response):
                print("[DEBUG] Resposta inválida, atualizando sessão para getManga...")
                headers = self._refresh_headers(link)
                response = Http.get(link, headers=headers, timeout=getattr(self, 'timeout', None))
            
            soup = BeautifulSoup(response.content, "html.parser")

            data = soup.select(self.query_title_for_uri)
            if not data:
                print(f"[DEBUG] Nenhum elemento encontrado com selector '{self.query_title_for_uri}'")
                print(f"[DEBUG] HTML retornado (primeiros 300 chars):\n{response.text[:300]}...")
                raise Exception("Não foi possível extrair o título do mangá")

            element = data.pop()
            title = element.get("content", "").strip() or element.text.strip()

            if not title:
                raise Exception("Título vazio ou não encontrado")

            return Manga(id=link, name=title)
        except Exception as e:
            print(f"[DEBUG] Erro em getManga: {e}")
            raise

    def getChapters(self, id: str) -> List[Chapter]:
        try:
            # Primeira tentativa com headers cacheados
            uri = urljoin(self.url, id)
            headers = self._get_headers(uri)
            
            response = Http.get(uri, headers=headers, timeout=getattr(self, 'timeout', None))
            
            # Verifica se a resposta é válida
            if not self._check_response_valid(response):
                print("[DEBUG] Resposta inválida, atualizando sessão para getChapters...")
                headers = self._refresh_headers(uri)
                response = Http.get(uri, headers=headers, timeout=getattr(self, 'timeout', None))
                
            soup = BeautifulSoup(response.content, 'html.parser')
            data = soup.select(self.query_title_for_uri)
            element = data.pop()
            title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
            dom = soup.select('body')[0]
            data = dom.select(self.query_chapters)
            placeholder = dom.select_one(self.query_placeholder)
            if placeholder:
                try:
                    data = self._get_chapters_ajax(id)
                except Exception:
                    try:
                        data = self._get_chapters_ajax_old(placeholder['data-id'])
                    except Exception:
                        pass
            chs = []
            for el in data:
                ch_id = self.get_root_relative_or_absolute_link(el, uri)
                ch_number = el.text.strip()
                ch_name = title
                chs.append(Chapter(ch_id, ch_number, ch_name))

            chs.reverse()
            return chs
        except Exception as e:
            print(f"[DEBUG] Erro em getChapters: {e}")
            # Se falhar, atualiza os headers e tenta novamente
            print("[DEBUG] Falha ao obter capítulos, atualizando sessão e tentando novamente...")
            self._refresh_headers(urljoin(self.url, f'manga/{id}/'))
            try:
                return self._get_chapters_ajax(id)
            except Exception as e:
                print(f"[DEBUG] Falha na segunda tentativa: {e}")
                raise

    def getPages(self, ch: Chapter) -> Pages:
        # Atualiza referer para a página do capítulo
        uri = urljoin(self.url, ch.id)
        current_headers = self._get_headers()
        current_headers = {
            **current_headers,
            'referer': uri
        }
        uri = self._add_query_params(uri, {'style': 'list'})
        response = Http.get(uri, headers=current_headers, timeout=getattr(self, 'timeout', None))
        
        # Retry se falhar (sessão expirada, etc.)
        if not self._check_response_valid(response):
            print("[DEBUG] Erro na resposta, tentando atualizar a sessão...")
            current_headers = self._refresh_headers(uri)
            current_headers['referer'] = uri
            response = Http.get(uri, headers=current_headers, timeout=getattr(self, 'timeout', None))
        
        soup = BeautifulSoup(response.content, 'html.parser')
        images = soup.select_one(self.get_div_page)
        image = images.select(self.get_pages) if images else []
        imgs = []
        for img in image:
            src = img.get('src') or img.get('data-src') or ''
            if src:
                imgs.append(src)
        
        if not imgs:
            print("[DEBUG] Nenhuma imagem encontrada, tentando novamente com headers atualizados...")
            current_headers = self._refresh_headers(uri)
            current_headers['referer'] = uri
            response = Http.get(uri, headers=current_headers, timeout=getattr(self, 'timeout', None))
            
            soup = BeautifulSoup(response.content, 'html.parser')
            images = soup.select_one(self.get_div_page)
            image = images.select(self.get_pages) if images else []
            for img in image:
                src = img.get('src') or img.get('data-src') or ''
                if src:
                    imgs.append(src)
        
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, imgs)
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        # Usa headers cached se não fornecidos
        if headers is None:
            headers = self._get_headers()
        if cookies is None and self._cookies_cache:
            # Converte cookie string para dict se necessário
            cookies = {}
            for cookie in self._cookies_cache.split(';'):
                if '=' in cookie:
                    key, value = cookie.strip().split('=', 1)
                    cookies[key] = value
        
        # Adiciona um referer genérico se não existir, para a primeira tentativa
        if 'referer' not in headers:
            headers['referer'] = self.url

        try:
            return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)
        except Exception as e:
            print(f"[DEBUG] Falha no download: {e}. Tentando atualizar a sessão...")
            # Se o download falhar, pode ser por sessão expirada. Atualiza e tenta de novo.
            new_headers = self._refresh_headers()
            if self._cookies_cache:
                cookies = {}
                for cookie in self._cookies_cache.split(';'):
                    if '=' in cookie:
                        key, value = cookie.strip().split('=', 1)
                        cookies[key] = value
            return DownloadUseCase().execute(pages=pages, fn=fn, headers=new_headers, cookies=cookies)


    def _get_chapters_ajax(self, manga_id):
        
        # Usa headers cached com referer específico
        current_headers = self._get_headers()
        current_headers = {
            **current_headers,
            'referer': urljoin(self.url, f'manga/{manga_id}/')
        }
        
        if not manga_id.endswith('/'):
            manga_id += '/'
        uri = urljoin(self.url, f'{manga_id}ajax/chapters/')
        response = Http.post(uri, headers=current_headers, timeout=getattr(self, 'timeout', None))
        
        # Verifica se a resposta é válida
        if not self._check_response_valid(response):
            print("[DEBUG] Resposta inválida no AJAX, atualizando sessão...")
            current_headers = self._refresh_headers(urljoin(self.url, f'manga/{manga_id}/'))
            current_headers['referer'] = urljoin(self.url, f'manga/{manga_id}/')
            response = Http.post(uri, headers=current_headers, timeout=getattr(self, 'timeout', None))
        
        data = self._fetch_dom(response, self.query_chapters)
        print(f"data: {data}")
        if data:
            return data
        else:
            raise Exception('No chapters found (new ajax endpoint)!')

    def _fetch_dom(self, response, selector):
        try:
            return super()._fetch_dom(response, selector)
        except Exception as e:
            print(f"[DEBUG] Erro ao fazer parse do DOM: {e}")
            if hasattr(response, 'text'):
                print(f"[DEBUG] Resposta contém: {response.text[:200]}...")
            return []

    def _add_query_params(self, url, params):
        # Adiciona parâmetros de query à URL
        if not params:
            return url
        
        separator = '&' if '?' in url else '?'
        param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{url}{separator}{param_str}"

    def __del__(self):
        """Cleanup ao destruir a instância"""
        global _GLOBAL_BROWSER
        try:
            if _GLOBAL_BROWSER:
                _GLOBAL_BROWSER.close()
        except:
            pass


