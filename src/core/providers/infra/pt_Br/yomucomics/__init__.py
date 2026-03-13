import re
from typing import List
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import requests
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.manga_reader_cms import MangaReaderCms
from core.config.login_data import insert_login, LoginData, get_login, delete_login


class YomuComicsProvider(MangaReaderCms):
    name = 'Yomu Comics'
    lang = 'pt-Br'
    domain = ['yomu.com.br']

    def __init__(self):
        self.url = 'https://yomu.com.br'
        self.path = '/'
        self.domain = 'yomu.com.br'

        self.link_obra = 'https://yomu.com.br/obra/'
        self.public_chapter = 'https://yomu.com.br/api/public/series/'
        self.public_images = 'https://yomu.com.br/api/public/chapters/'
        self.query_mangas = 'ul.manga-list li a'
        self.query_chapters = 'div#chapterlist ul li'
        self.query_pages = 'div#readerarea img'
        self.query_title_for_uri = 'h1'

    def getManga(self, link: str) -> Manga:
        response = requests.get(link)
        print(f"response: {response.status_code}")
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.query_title_for_uri).text.strip()
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        # 'https://yomu.com.br/api/public/series/providencia-de-alto-nivel'
        url = id.replace(self.link_obra, self.public_chapter)

        response = Http.get(url)
        data = response.json()
        chapters = data.get('chapters', [])
        indexes = [chapter['index'] for chapter in chapters]

        base_url = id.replace("obra", "ler")
        title = data.get("name")
        id = data.get("id")
        title = f"{title} - {id}"
        chapters = []
        for element in indexes:
            link = f"{base_url}/{element}"
            chapters.append(Chapter(
                id=link,
                number=str(element),
                name=title
            ))
        chapters.reverse()
        return chapters

    
    def getPages(self, ch: Chapter) -> Pages:
        # https://yomu.com.br/api/public/chapters/93/54
        title, id = ch.name.split(" - ")
        ch.name = title
        images = f"{self.public_images}{id}/{ch.number}"
        print(f"images: {images}")
        list = []
        response = Http.get(images)
        pages = response.json().get("pages", [])
        for page in pages:
            url = page.get("url")
            if url:
                list.append(urljoin(self.url, url))
        return Pages(ch.id, ch.number, ch.name, list)