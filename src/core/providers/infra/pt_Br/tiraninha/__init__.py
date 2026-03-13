import re
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.wordpress_madara import WordPressMadara
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs
from core.config.login_data import insert_login, LoginData, get_login, delete_login
from threading import Lock
import requests

_login_lock = Lock()

class TiraninhaProvider(WordPressMadara):
    name = 'Tiraninha'
    lang = 'pt_Br'
    domain = ['tiraninha.world']
    has_login = True

    def __init__(self):
        super().__init__()
        self.url = 'https://tiraninha.world/'
        self.login_url = urljoin(self.url, 'wp-login.php')

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.reading-content div.page-break'
        self.query_title_for_uri = 'div.post-title h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        
        self.username = "opai@gmail.com"
        self.password = "Opai@123"
        self.session_cookies = None

    def _get_headers(self) -> dict:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        if self.session_cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in self.session_cookies.items()])
            headers['Cookie'] = cookie_str
            
        return headers

    def _login_via_form(self) -> dict:
        try:
            session = requests.Session()
            session.headers.update(self._get_headers())
            
            response = session.get(self.login_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            wp_submit = soup.find("input", {"name": "wp-submit"})
            redirect_to = soup.find("input", {"name": "redirect_to"})
            testcookie = soup.find("input", {"name": "testcookie"})
            
            data = {
                "log": self.username,
                "pwd": self.password,
                "wp-submit": wp_submit["value"] if wp_submit else "Acessar",
                "redirect_to": redirect_to["value"] if redirect_to else urljoin(self.url, "wp-admin/"),
                "testcookie": testcookie["value"] if testcookie else "1",
            }
            
            post_response = session.post(self.login_url, data=data)
            
            if post_response.status_code != 200:
                err_soup = BeautifulSoup(post_response.text, "html.parser")
                err_el = err_soup.find(id="login_error")
                post_response.raise_for_status()
            
            cookies = session.cookies.get_dict()
            
            if any(k.startswith('wordpress_logged_in_') for k in cookies.keys()):
                return cookies
            else:
                raise Exception("Cookies de login do WordPress não encontrados após o POST.")
                
        except Exception as e:
            raise Exception(f"Falha no login: {e}")

    def login(self):
        if self.session_cookies:
            return

        with _login_lock:
            if self.session_cookies:
                return

            login_info = get_login(self.domain[0])
            
            if login_info and login_info.cookies:
                self.session_cookies = login_info.cookies
                return

            cookies = self._login_via_form()
            self.session_cookies = cookies

            insert_login(LoginData(self.domain[0], {}, cookies))

    def _check_auth_error(self, html_content: str) -> bool:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        login_form = soup.find("form", id="loginform")
        if login_form:
            return True
            
        pass_form = soup.find("form", class_="post-password-form")
        if pass_form:
            return True

        return False

    def _http_get_with_login(self, url: str) -> requests.Response:
        self.login()
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers, timeout=getattr(self, 'timeout', 30))
        
        if self._check_auth_error(response.text):
            delete_login(self.domain[0])
            self.session_cookies = None
            self.login()
            headers = self._get_headers()
            response = requests.get(url, headers=headers, timeout=getattr(self, 'timeout', 30))
            
        return response

    def _http_post_with_login(self, url: str, data: dict = None) -> requests.Response:
        self.login()
        headers = self._get_headers()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        
        response = requests.post(url, headers=headers, data=data, timeout=getattr(self, 'timeout', 30))
        
        if self._check_auth_error(response.text):
            delete_login(self.domain[0])
            self.session_cookies = None
            self.login()
            headers = self._get_headers()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers['X-Requested-With'] = 'XMLHttpRequest'
            response = requests.post(url, headers=headers, data=data, timeout=getattr(self, 'timeout', 30))
            
        return response

    def getManga(self, link: str) -> Manga:
        response = self._http_get_with_login(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_title_for_uri)
        if not data:
            data = soup.select('div.post-title h3')
        if not data:
             data = soup.select('div.post-title h2')
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        return Manga(id=link, name=title)

    def getChapters(self, id: str) -> List[Chapter]:
        uri = urljoin(self.url, id)
        response = self._http_get_with_login(uri)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        data = soup.select(self.query_title_for_uri)
        if not data:
             data = soup.select('div.post-title h3')
        if not data:
             data = soup.select('div.post-title h2')
             
        element = data.pop()
        title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
        
        dom = soup.select('body')[0]
        data = dom.select(self.query_chapters)
        placeholder = dom.select_one(self.query_placeholder)
        
        if placeholder:
            try:
                data = self._get_chapters_ajax_with_session(id)
            except Exception as e:
                try:
                    data = self._get_chapters_ajax_old_with_session(placeholder['data-id'])
                except Exception as e:
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
        try:
            uri = urljoin(self.url, ch.id)
            uri = self._add_query_params(uri, {'style': 'paged'})
            
            response = self._http_get_with_login(uri)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            data = soup.select_one('script#chapter_preloaded_images')
            if data:
                pattern = r'https:\\/\\/[^\"]+'
                links = re.findall(pattern, data.get_text(strip=True))
                list_imgs = [link.replace('\\/', '/') for link in links]
            else:
                 page_data = soup.select(self.query_pages)
                 list_imgs = []
                 for el in page_data:
                      img_el = el.find('img') or el.find('image')
                      if img_el:
                          src = img_el.get('data-src') or img_el.get('data-lazy-src') or img_el.get('src')
                          if src:
                               list_imgs.append(src.strip())
            
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else str(ch.number)
            return Pages(ch.id, number, ch.name, list_imgs)
        except Exception as e:
            raise e

    def _get_chapters_ajax_old_with_session(self, data_id):
        uri = urljoin(self.url, f'{self.path}/wp-admin/admin-ajax.php')
        data = {'action': 'manga_get_chapters', 'manga': data_id}
        response = self._http_post_with_login(uri, data=data)
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.select(self.query_chapters)

    def _get_chapters_ajax_with_session(self, manga_id):
        if not manga_id.endswith('/'):
            manga_id += '/'
        uri = urljoin(self.url, f'{manga_id}ajax/chapters/')
        response = self._http_post_with_login(uri)
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.select(self.query_chapters)
