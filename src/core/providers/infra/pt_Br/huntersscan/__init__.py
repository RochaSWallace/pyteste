import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fake_useragent import UserAgent
from typing import List
from selenium import webdriver
import time
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Pages
from core.download.application.use_cases import DownloadUseCase
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.wordpress_madara import WordPressMadara

class HuntersScanProvider(WordPressMadara):
    name = 'Hunters scan'
    lang = 'pt-Br'
    domain = ['readhunters.xyz']

    def __init__(self):
        self.url = 'https://readhunters.xyz'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_pages_img = 'div.reading-content img.wp-manga-chapter-img'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        ua = UserAgent()
        user = ua.chrome
        self.headers = {'host': 'readhunters.xyz', 'user_agent': user, 'referer': f'{self.url}/series', 'Cookie': 'acesso_legitimo=1'}
        self.timeout=3
    
    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
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
                pass

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
        Primeiro tenta extrair diretamente do HTML usando Selenium + BeautifulSoup.
        Se falhar, usa o método antigo de PerformanceObserver.
        """
        uri = urljoin(self.url, ch.id)
        
        # Método 1: Extração direta do HTML usando Selenium
        try:
            urls_imagens = self._get_images_http(uri)
            if urls_imagens:
                number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
                return Pages(ch.id, number, ch.name, urls_imagens)
        except Exception as e:
            print(f"Falha no método de extração HTML: {e}")
        
        # Método 2: Fallback para o método antigo usando PerformanceObserver
        try:
            urls_imagens = self._extrair_urls_performance_observer(uri)
            if urls_imagens:
                number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
                return Pages(ch.id, number, ch.name, urls_imagens)
        except Exception as e:
            print(f"Falha no método PerformanceObserver: {e}")
            raise Exception("Não foi possível extrair as URLs das imagens do capítulo")
    
    def _get_images_http(self, url_capitulo):
        """
        Usa requisição HTTP direta para obter o HTML e BeautifulSoup para extrair os links das imagens.
        As imagens já estão renderizadas no HTML com atributo src completo.
        """
        try:
            # Fazer requisição HTTP direta
            response = Http.get(
                url_capitulo, 
                headers=self.headers,
                timeout=getattr(self, 'timeout', None)
            )
            
            # Parsear com BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar as imagens usando a query configurada
            imagens = soup.select(self.query_pages_img)
            
            if not imagens:
                print(f"Nenhuma imagem encontrada com o seletor: {self.query_pages_img}")
                return []
            
            # Extrair URLs das imagens
            urls_imagens = []
            for img in imagens:
                # Tentar atributos diferentes onde a URL pode estar
                src = img.get('src', '').strip()
                data_src = img.get('data-src', '').strip()
                data_lazy_src = img.get('data-lazy-src', '').strip()
                
                # Priorizar o atributo que contém a URL completa
                url = src or data_src or data_lazy_src
                
                if url and '/WP-manga/data/' in url:
                    # Remover espaços em branco extras que podem estar na URL
                    url = url.strip()
                    urls_imagens.append(url)
            
            if not urls_imagens:
                print("Nenhuma URL de imagem válida foi extraída.")
                return []
            
            # Ordenar as URLs pelo número no nome do arquivo
            def extrair_numero(url):
                try:
                    nome_arquivo = url.split('/')[-1]
                    # Extrair apenas os dígitos do nome do arquivo
                    numero = nome_arquivo.split('.')[0]
                    return int(numero)
                except (ValueError, IndexError):
                    return 0
            
            urls_ordenadas = sorted(urls_imagens, key=extrair_numero)
            
            print(f"Total de {len(urls_ordenadas)} imagens extraídas e ordenadas.")
            return urls_ordenadas
            
        except Exception as e:
            print(f"Erro ao extrair URLs via HTTP: {e}")
            return []
    
    def _extrair_urls_performance_observer(self, url_capitulo):
        """
        Usa selenium-stealth e PerformanceObserver para extrair as URLs.
        Método antigo mantido como fallback.
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        chrome_options.add_argument('--ignore-certificate-errors')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        urls_para_bloquear = [
            "*googlesyndication.com*",
            "*googletagmanager.com*",
            "*google-analytics.com*",
            "*disable-devtool*",
            "*adblock-checker*",
        ]
        
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': urls_para_bloquear})

        stealth(driver,
                languages=["pt-BR", "pt"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
        )

        driver.get(url_capitulo)

        script_js = """
            window.originalImageUrls = new Set();
            const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (entry.initiatorType === 'img' && entry.name.includes('/WP-manga/data/')) {
                window.originalImageUrls.add(entry.name);
                }
            }
            });
            observer.observe({ type: "resource", buffered: true });
            return true; 
        """

        driver.execute_script(script_js)

        urls_capturadas = driver.execute_script("return Array.from(window.originalImageUrls);")

        driver.quit()

        if not urls_capturadas:
            print("Nenhuma URL foi capturada pelo PerformanceObserver.")
            return []

        def extrair_numero(url):
            try:
                nome_arquivo = url.split('/')[-1]
                return int(nome_arquivo.split('.')[0])
            except (ValueError, IndexError):
                return 0

        urls_ordenadas = sorted(urls_capturadas, key=extrair_numero)
        return urls_ordenadas
    
    
    def _get_chapters_ajax(self, manga_id):
        if not manga_id.endswith('/'):
            manga_id += '/'
        data = []
        t = 1
        while True:
            uri = urljoin(self.url, f'{manga_id}ajax/chapters/?t={t}')
            response = Http.post(uri, timeout=getattr(self, 'timeout', None))
            chapters = self._fetch_dom(response, self.query_chapters)
            if chapters:
                data.extend(chapters)
                t += 1
            else:
                break
        if data:
            return data
        else:
            raise Exception('No chapters found (new ajax endpoint)!')
    
    def _get_chapters_ajax_old(self, data_id):
        uri = urljoin(self.url, f'{self.path}/wp-admin/admin-ajax.php')
        response = Http.post(uri, data=f'action=manga_get_chapters&manga={data_id}', headers={
            'content-type': 'application/x-www-form-urlencoded',
            'x-referer': self.url
        }, timeout=getattr(self, 'timeout', None))
        data = self._fetch_dom(response, self.query_chapters)
        if data:
            return data
        else:
            raise Exception('No chapters found (old ajax endpoint)!')

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        if headers is not None:
            headers = headers | self.headers
        else:
            headers = self.headers
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies, timeout=self.timeout)