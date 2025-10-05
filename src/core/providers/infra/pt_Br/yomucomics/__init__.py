import re
import requests
from typing import List
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.manga_reader_cms import MangaReaderCms
from core.config.login_data import insert_login, LoginData, get_login, delete_login


class YomuComicsProvider(MangaReaderCms):
    name = 'Yomu Comics'
    lang = 'pt-Br'
    domain = ['yomu.com.br']
    has_login = True

    def __init__(self):
        super().__init__()
        self.url = 'https://yomu.com.br'
        self.path = '/'
        self.login_page = 'https://yomu.com.br/auth/login'
        self.domain = 'yomu.com.br'

        self.link_obra = 'https://yomu.com.br/obra/'
        self.public_chapter = 'https://yomu.com.br/api/public/series/'
        self.public_images = 'https://yomu.com.br/api/public/chapters/'
        self.query_mangas = 'ul.manga-list li a'
        self.query_chapters = 'div#chapterlist ul li'
        self.query_pages = 'div#readerarea img'
        self.query_title_for_uri = 'h1'

    def _is_login_page(self, html) -> bool:
        soup = BeautifulSoup(html, 'html.parser')

        title = soup.title.string if soup.title else ""
        if "login" in title.lower():
            return True
        
        return False
    
    def login(self):
        """Login via API - execução simplificada para evitar conflitos de threading"""
        # Verifica se já tem login salvo (não faz requisições aqui)
        login_info = get_login(self.domain)
        if login_info:
            print("[YomuComics] ✅ Login encontrado em cache")
            return True
        
        print("[YomuComics] ⚠️  Nenhum login encontrado")
        print("[YomuComics] 📝 Faça login manualmente no navegador em: https://yomu.com.br")
        
        # Tenta fazer login via API de forma simples
        try:
            session = requests.Session()
            
            login_data = {
                'email': 'opai@gmail.com',
                'password': 'Opaiec@lvo1'
            }
            
            response = session.post(
                self.login_page,
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                timeout=15
            )
            
            # Se status OK, salva cookies
            if response.status_code == 200:
                cookies_dict = {}
                for cookie in session.cookies:
                    cookies_dict[cookie.name] = cookie.value
                
                if cookies_dict:
                    insert_login(LoginData(self.domain, {}, cookies_dict))
                    print(f"[YomuComics] ✅ {len(cookies_dict)} cookies salvos")
                    return True
            
            print(f"[YomuComics] ⚠️  Status: {response.status_code}")
            return False
            
        except Exception as e:
            print(f"[YomuComics] ⚠️  Erro no login automático: {e}")
            print("[YomuComics] 💡 O provider funcionará para conteúdo público")
            return False

    def getManga(self, link: str) -> Manga:
        url = link.replace(self.link_obra, self.public_chapter)
        response = Http.get(url)
        data = response.json()
        title = data.get("name")
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