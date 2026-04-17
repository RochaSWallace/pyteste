from time import sleep
from typing import List
from DrissionPage import ChromiumPage, ChromiumOptions
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs
from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.config.login_data import insert_login, LoginData, get_login


class CorujaToonsProvider(WordPressMadara):
    name = 'Coruja Toons'
    lang = 'pt_Br'
    domain = ['corujatoon.com']
    has_login = True

    def __init__(self):
        super().__init__()
        self.url = 'https://corujatoon.com'
        self.domain_name = 'corujatoon.com'
        self.login_url = f'{self.url}/login'
        self.query_chapters = 'div[class*="grid gap-3 max-h-[500px] md:max-h-[600px] overflow-y-auto pr-2 custom-scrollbar"] a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.w-full.flex.justify-center.relative[class*="min-h-[300px]"]'
        self.query_title_for_uri = 'h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.path = ''

    def login(self):
        login_info = get_login(self.domain_name)
        if login_info:
            print('[CorujaToons] Login encontrado em cache')
            return True

        print('[CorujaToons] Iniciando navegador para login...')
        print('[CorujaToons] Voce tem 30 segundos para fazer login')

        page = None
        try:
            co = ChromiumOptions()
            co.headless(False)

            page = ChromiumPage(addr_or_opts=co)
            page.get(self.login_url)

            print('[CorujaToons] Aguardando 30 segundos...')
            sleep(30)

            cookies = page.cookies()
            cookies_dict = {}

            for cookie in cookies:
                if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                    cookies_dict[cookie.name] = cookie.value
                elif isinstance(cookie, dict):
                    name = cookie.get('name')
                    value = cookie.get('value')
                    if name and value:
                        cookies_dict[name] = value

            if not cookies_dict:
                print('[CorujaToons] Nenhum cookie capturado')
                return False

            insert_login(LoginData(self.domain_name, {}, cookies_dict))
            print(f'[CorujaToons] Login salvo com sucesso ({len(cookies_dict)} cookies)')
            return True

        except ImportError:
            print('[CorujaToons] DrissionPage nao esta instalado. Execute: pip install DrissionPage')
            return False
        except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError) as e:
            print(f'[CorujaToons] Erro durante login: {e}')
            return False
        finally:
            if page:
                try:
                    page.quit()
                except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError):
                    pass

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
                try:
                    data = self._get_chapters_ajax_old(placeholder['data-id'])
                except Exception:
                    pass

        chs = []
        for el in data:
            ch_id = self.get_root_relative_or_absolute_link(el, uri)
            href = (el.get('href') or '').strip()

            chapter_slug = ''
            if '/capitulo/' in href:
                chapter_slug = href.split('/capitulo/', 1)[1]
                chapter_slug = chapter_slug.split('?', 1)[0].split('#', 1)[0].strip('/')

            ch_number = chapter_slug.replace('-', '.') if chapter_slug else ''
            if not ch_number:
                heading = el.select_one('h3')
                ch_number = (heading.text.strip() if heading else el.text.strip())

            if not ch_number:
                continue

            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs