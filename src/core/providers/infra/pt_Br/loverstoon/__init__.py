from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from bs4 import BeautifulSoup
import re
from core.__seedwork.infra.http import Http
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs
from bs4 import BeautifulSoup
import time
import atexit
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Lista global para rastrear todos os drivers criados
_ACTIVE_DRIVERS = []
_DRIVERS_LOCK = threading.Lock()

def _register_driver(driver):
    """Registra um driver na lista de drivers ativos"""
    with _DRIVERS_LOCK:
        _ACTIVE_DRIVERS.append(driver)

def _cleanup_all_drivers():
    """Fecha todos os drivers ativos ao encerrar o programa"""
    with _DRIVERS_LOCK:
        for driver in _ACTIVE_DRIVERS:
            try:
                driver.quit()
            except:
                pass
        _ACTIVE_DRIVERS.clear()

# Registra a função de cleanup para ser chamada ao encerrar o programa
atexit.register(_cleanup_all_drivers)

class LoversToonProvider(WordPressMadara):
    name = 'Lovers toon'
    lang = 'pt-Br'
    domain = ['loverstoon.com']

    def __init__(self):
        self.url = 'https://loverstoon.com'
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'img'
        self.query_title_for_uri = 'h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'

    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup_real = BeautifulSoup(response.content, 'html.parser')
        real_link = soup_real.select_one("div.page-break > a").get('href')
        soup = self._getRealPages(real_link)
        data = soup.select(self.query_pages)
        list = [] 
        for el in data:
            list.append(el.get("src") or el.get("data-src"))

        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, list)
    
    def _getRealPages(self, uri: str) -> BeautifulSoup:
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
        
        # Registrar o driver para cleanup automático
        _register_driver(driver)
        
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
        
        driver.get(uri)
        time.sleep(4)  # Aguarda o carregamento da página
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Fechar o driver após uso
        try:
            driver.quit()
        except:
            pass
            
        return soup