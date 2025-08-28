from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from bs4 import BeautifulSoup
import time
import undetected_chromedriver as uc
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

class ArgosComicProvider(WordpressEtoshoreMangaTheme):
    name = 'Argos Comic'
    lang = 'pt_Br'
    domain = ['argoscomic.com']

    def __init__(self):
        self.url = 'https://argoscomic.com'
        self.link = 'https://argoscomic.com/'

        self.get_title = 'h1.text-2xl'
        self.get_chapters_list = 'div.space-y-6'
        self.chapter = 'a'
        self.get_chapter_number = 'span.font-medium'
        self.get_div_page = 'div.flex.flex-col.items-center'
        self.get_pages = 'img'
    
    def getManga(self, link: str) -> Manga:
        self._driver = self._open_driver(link)
        html = self._driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.select_one(self.get_title)
        print(title)
        return Manga(link, title.get_text().strip())


    def getChapters(self, id: str) -> List[Chapter]:
        driver = getattr(self, '_driver', None)
        if driver is None:
            driver = self._open_driver(id)

        try:
            driver.get(id)
            try:
                wait = WebDriverWait(driver, 5)
                load_more_button = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Carregar mais capítulos')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
                
                driver.execute_script("arguments[0].click();", load_more_button)

            except TimeoutException:
                print("Botão 'Carregar mais capítulos' não encontrado. Extraindo capítulos já visíveis. 👍")


            time.sleep(3)
            volumes = driver.find_elements(By.XPATH, "//h2[contains(text(), 'Volume')]/ancestor::div[contains(@class, 'cursor-pointer')]")
            if volumes:
                for vol in volumes:
                    try:
                        svg = vol.find_element(By.TAG_NAME, "svg")
                        path = svg.find_element(By.TAG_NAME, "path")
                        d = path.get_attribute("d")
                        if d and d.strip().startswith("M17.919"):
                            print(f"Volume fechado encontrado, expandindo...")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", vol)
                            # time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", vol)
                            # time.sleep(1)
                    except Exception as e:
                        print(f"Erro ao tentar expandir volume: {e}")
                
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            chapters_list = soup.select_one(self.get_chapters_list)
            chapter = chapters_list.select(self.chapter)
            title = soup.select_one(self.get_title)
            list = []
            for ch in chapter:
                number = ch.select_one(self.get_chapter_number)
                list.append(Chapter(f"{self.url}{ch.get('href')}", number.get_text().strip(), title.get_text().strip()))
            driver.quit()
            return list

        finally:
            if hasattr(self, '_driver'):
                self._driver.quit()
                del self._driver

    def getPages(self, ch: Chapter) -> Pages:
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-dev-shm-usage')
        # Desabilita imagens para economizar recursos
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)
        print(ch.id)
        with uc.Chrome(options=options) as driver:
            driver.get(ch.id)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            scroll_script = '''
            var elements = document.querySelectorAll('*');
            for (var i = 0; i < elements.length; i++) {
                var el = elements[i];
                var style = window.getComputedStyle(el);
                if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                    el.scrollTop = el.scrollHeight;
                }
            }
            '''
            driver.execute_script(scroll_script)
            time.sleep(1)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            # div_pages = soup.select_one(self.get_div_page)
            img_urls = []
            img_tags = soup.find_all(self.get_pages)
            for img in img_tags:
                src = img.get('src')
                if src:
                    img_urls.append(src)
            
            
            # if div_pages:
            #     images = div_pages.select(self.get_pages)
            #     for img in images:
            #         src = img.get('src')
            #         if src:
            #             img_urls.append(src)
            return Pages(ch.id, ch.number, ch.name, img_urls)
    
    def _open_driver(self, url):
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-dev-shm-usage')
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)
        driver = uc.Chrome(options=options)
        driver.get(url)
        time.sleep(1)  # Aguarda o carregamento inicial
        return driver
