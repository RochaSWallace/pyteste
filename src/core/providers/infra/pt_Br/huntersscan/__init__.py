import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fake_useragent import UserAgent
from typing import List
from selenium import webdriver
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

    
    def extrair_urls_do_capitulo(url_capitulo):
        """
        Usa selenium-stealth e bloqueio de rede nativo (CDP) para extrair as URLs.
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-client-side-phishing-detection')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-hang-monitor')
        chrome_options.add_argument('--disable-prompt-on-repost')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--safebrowsing-disable-auto-update')
        chrome_options.add_argument('--disable-features=site-per-process,TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--window-size=800,600')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        urls_para_bloquear = [
            "*googlesyndication.com*",
            "*googletagmanager.com*",
            "*google-analytics.com*",
            "*disable-devtool*", # Padrão comum em scripts anti-debug
            "*adblock-checker*", # Padrão comum em detectores de adblock
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
        # time.sleep(5)

        urls_capturadas = driver.execute_script("return Array.from(window.originalImageUrls);")

        driver.quit()

        if not urls_capturadas:
            print("Nenhuma URL foi capturada.")
            return []

        def extrair_numero(url):
            try:
                nome_arquivo = url.split('/')[-1]
                return int(nome_arquivo.split('.')[0])
            except (ValueError, IndexError):
                return 0

        urls_ordenadas = sorted(urls_capturadas, key=extrair_numero)
        return urls_ordenadas
    
    def getPages(self, ch: Chapter) -> Pages:
        
        def extrair_urls_do_capitulo(url_capitulo):
            """
            Usa selenium-stealth e bloqueio de rede nativo (CDP) para extrair as URLs.
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
            # time.sleep(5)

            urls_capturadas = driver.execute_script("return Array.from(window.originalImageUrls);")

            driver.quit()

            if not urls_capturadas:
                print("Nenhuma URL foi capturada.")
                return []

            def extrair_numero(url):
                try:
                    nome_arquivo = url.split('/')[-1]
                    return int(nome_arquivo.split('.')[0])
                except (ValueError, IndexError):
                    return 0

            urls_ordenadas = sorted(urls_capturadas, key=extrair_numero)
            return urls_ordenadas
    
        uri = urljoin(self.url, ch.id)
        urls_originais = extrair_urls_do_capitulo(uri)

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, urls_originais)
    
    
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

    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        if headers is not None:
            headers = headers | self.headers
        else:
            headers = self.headers
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies, timeout=self.timeout)