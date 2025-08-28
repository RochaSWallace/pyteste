from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class ApeComicsProvider(WordpressEtoshoreMangaTheme):
    name = 'Ape Comics'
    lang = 'pt_Br'
    domain = ['apecomics.net']

    def __init__(self) -> None:
        self.url = 'https://apecomics.net'
        self.link = 'https://apecomics.net'
        self.get_title = 'h1'
        self.get_chapters_list = 'div.eplister#chapterlist > ul'
        self.chapter = 'li a'
        self.get_chapter_number = 'span.chapternum'
        self.get_div_page = 'div#readerarea'
        self.get_pages = 'img'
    
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


