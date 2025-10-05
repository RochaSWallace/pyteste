import re
import asyncio
import nodriver as uc
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages
from core.providers.infra.template.manga_reader_cms import MangaReaderCms
from core.config.login_data import insert_login, LoginData, get_login, delete_login
import base64
from typing import List
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from urllib.parse import unquote, urljoin, urlparse
from core.providers.domain.entities import Chapter, Pages, Manga


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
        print("login")
        login_info = get_login(self.domain)
        if login_info:
            response  = Http.get(self.url)
            if self._is_login_page(response.content):
                delete_login(self.domain)
                login_info = None
            
        if not login_info:
            async def getLogin():
                browser = await uc.start()
                # ✅ CREDENCIAIS PRÉ-DEFINIDAS
                LOGIN_EMAIL = "opai@gmail.com"
                LOGIN_PASSWORD = "Opaiec@lvo1"
                
                page = await browser.get(self.login_page)
                
                print("🔐 Fazendo login automático...")
                
                try:
                    # Aguarda a página carregar completamente
                    await asyncio.sleep(3)
                    
                    # ✅ PREENCHE EMAIL
                    email_input = await page.select('#email')
                    if email_input:
                        await email_input.send_keys(LOGIN_EMAIL)
                        print(f"✅ Email preenchido: {LOGIN_EMAIL}")
                    else:
                        print("❌ Campo email não encontrado")
                        # Tenta seletores alternativos
                        email_input = await page.select('input[name="email"]')
                        if email_input:
                            await email_input.send_keys(LOGIN_EMAIL)
                            print("✅ Email preenchido com seletor alternativo")
                    
                    # ✅ PREENCHE SENHA
                    password_input = await page.select('#password')
                    if password_input:
                        await password_input.send_keys(LOGIN_PASSWORD)
                        print("✅ Senha preenchida")
                    else:
                        print("❌ Campo senha não encontrado")
                        # Tenta seletores alternativos
                        password_input = await page.select('input[name="password"]')
                        if password_input:
                            await password_input.send_keys(LOGIN_PASSWORD)
                            print("✅ Senha preenchida com seletor alternativo")
                    
                    # ✅ CLICA NO BOTÃO DE LOGIN
                    login_button = await page.select('button[type="submit"]')
                    if login_button:
                        await login_button.click()
                        print("✅ Botão de login clicado")
                    else:
                        # Tenta seletores alternativos para o botão
                        login_button = await page.select('button:contains("Entrar")')
                        if login_button:
                            await login_button.click()
                            print("✅ Botão 'Entrar' clicado")
                        else:
                            print("❌ Botão de login não encontrado")
                    
                    # ✅ AGUARDA LOGIN SER PROCESSADO
                    print("⏳ Aguardando processamento do login...")
                    login_attempts = 0
                    max_attempts = 30  # 30 segundos máximo
                    
                    while login_attempts < max_attempts:
                        await asyncio.sleep(1)
                        login_attempts += 1
                        
                        # Verifica se ainda está na página de login
                        html_page = await page.get_content()
                        current_url = page.url
                        
                        # Se não está mais na página de login, login foi bem-sucedido
                        if not self._is_login_page(html_page) or '/auth/login' not in current_url:
                            print(f"✅ Login bem-sucedido! URL atual: {current_url}")
                            
                            # ✅ CAPTURA COOKIES DE AUTENTICAÇÃO
                            cookies = await browser.cookies.get_all()
                            auth_cookie_found = False
                            
                            for cookie in cookies:
                                # Procura por diferentes tipos de cookies de autenticação
                                if (cookie.name.startswith('wordpress_logged_in_') or 
                                    'auth' in cookie.name.lower() or
                                    'session' in cookie.name.lower() or
                                    'token' in cookie.name.lower()):
                                    
                                    print(f"🍪 Cookie de autenticação encontrado: {cookie.name}")
                                    insert_login(LoginData(self.domain, {}, {cookie.name: cookie.value}))
                                    auth_cookie_found = True
                            
                            # Se não encontrou cookies específicos, salva todos os cookies do domínio
                            if not auth_cookie_found:
                                all_cookies = {}
                                for cookie in cookies:
                                    if 'yomu' in cookie.domain or 'com.br' in cookie.domain:
                                        all_cookies[cookie.name] = cookie.value
                                
                                if all_cookies:
                                    print(f"🍪 Salvando {len(all_cookies)} cookies do domínio")
                                    insert_login(LoginData(self.domain, {}, all_cookies))
                            
                            break
                        
                        # Verifica se houve erro de login
                        if 'erro' in html_page.lower() or 'invalid' in html_page.lower():
                            print("❌ Erro de login detectado - credenciais inválidas?")
                            break
                    
                    if login_attempts >= max_attempts:
                        print("⏰ Timeout no login - fallback para login manual")
                        # Fallback para login manual
                        while True:
                            html_page = await page.get_content()
                            if self._is_login_page(html_page):
                                await asyncio.sleep(1)
                            else:
                                cookies = await browser.cookies.get_all()
                                for cookie in cookies:
                                    if cookie.name.startswith('wordpress_logged_in_'):
                                        insert_login(LoginData(self.domain, {}, {cookie.name: cookie.value}))
                                        break
                                break
                
                except Exception as e:
                    print(f"❌ Erro durante login automático: {e}")
                    print("🔄 Fallback para login manual...")
                    # Fallback para o método original
                    while True:
                        html_page = await page.get_content()
                        if self._is_login_page(html_page):
                            sleep(1)
                        else:
                            cookies = await browser.cookies.get_all()
                            for cookie in cookies:
                                if cookie.name.startswith('wordpress_logged_in_'):
                                    insert_login(LoginData(self.domain, {}, {cookie.name: cookie.value}))
                                    break
                            break
                
                browser.stop()
            uc.loop().run_until_complete(getLogin())
    
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