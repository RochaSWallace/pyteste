from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class PlumaComicsProvider(WordpressEtoshoreMangaTheme):
    name = 'Pluma Comics'
    lang = 'pt_Br'
    domain = ['plumacomics.cloud']

    def __init__(self) -> None:
        self.url = 'https://plumacomics.cloud'
        self.link = 'https://plumacomics.cloud'
        self.get_title = 'h1'
        self.get_chapters_list = 'div.eplister#chapterlist > ul'
        self.chapter = 'li a'
        self.get_chapter_number = 'span.chapternum'
        self.get_div_page = 'div#readerarea'
        self.get_pages = 'img.ts-main-image'
    
    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)
        return Manga(link, title.get_text().strip())

    def getChapters(self, id: str) -> List[Chapter]:
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        chapters_list = soup.select_one(self.get_chapters_list)
        chapter = chapters_list.select(self.chapter)
        title = soup.select_one(self.get_title)
        list = []
        for ch in chapter:
            number = ch.select_one(self.get_chapter_number)
            list.append(Chapter(ch.get('href'), number.get_text().strip(), title.get_text().strip()))
        return list

    def getPages(self, ch: Chapter) -> Pages:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # Desabilita imagens para economizar recursos
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)

        driver = webdriver.Chrome(options=options)
        try:
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    driver.get(ch.id)
                    break
                except Exception as e:
                    print(f"Erro ao carregar página (tentativa {attempt+1}): {e}")
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            div_pages = soup.select_one(self.get_div_page)
            images = div_pages.select(self.get_pages) if div_pages else []
            img_urls = [img.get('data-src') or img.get('src') for img in images]
            return Pages(ch.id, ch.number, ch.name, img_urls)
        finally:
            driver.quit()
