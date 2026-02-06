import re
from typing import List
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from DrissionPage import ChromiumPage, ChromiumOptions
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
        """Login manual usando DrissionPage para capturar cookies do navegador"""
        # Verifica se já tem login salvo
        login_info = get_login(self.domain)
        if login_info:
            print("[YomuComics] ✅ Login encontrado em cache")
            return True
        
        print("[YomuComics] 🔐 Iniciando navegador para login...")
        print("[YomuComics] 📝 Você tem 30 segundos para fazer login manualmente")
        
        try:
            # Configurar opções do navegador
            co = ChromiumOptions()
            co.headless(False)
            
            # Criar página
            page = ChromiumPage(addr_or_opts=co)
            page.get(self.login_page)
            
            print("[YomuComics] ⏳ Aguardando 30 segundos...")
            sleep(30)
            
            print("[YomuComics] ✅ Capturando cookies...")
            
            # Captura todos os cookies
            cookies = page.cookies()
            cookies_dict = {}
            
            # DrissionPage retorna um objeto CookiesList
            for cookie in cookies:
                if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                    cookies_dict[cookie.name] = cookie.value
                elif isinstance(cookie, dict):
                    cookies_dict[cookie.get('name')] = cookie.get('value')
            
            print(f"[YomuComics] 🍪 {len(cookies_dict)} cookies capturados")
            
            # Fecha o navegador
            page.quit()
            
            # Salva os cookies
            if cookies_dict:
                insert_login(LoginData(self.domain, {}, cookies_dict))
                print("[YomuComics] ✅ Login realizado e cookies salvos com sucesso!")
                return True
            else:
                print("[YomuComics] ⚠️  Nenhum cookie capturado")
                return False
                
        except ImportError:
            print("[YomuComics] ❌ DrissionPage não está instalado")
            print("[YomuComics] Execute: pip install DrissionPage")
            return False
        except Exception as e:
            print(f"[YomuComics] ❌ Erro durante login: {e}")
            import traceback
            traceback.print_exc()
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