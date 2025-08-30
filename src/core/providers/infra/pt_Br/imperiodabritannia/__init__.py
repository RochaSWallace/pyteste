from urllib.parse import urljoin
import re
from typing import List
from fake_useragent import UserAgent
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.application.use_cases import DownloadUseCase
from core.providers.infra.template.wordpress_madara import WordPressMadara

class ImperiodabritanniaProvider(WordPressMadara):
    name = 'Imperio da britannia'
    lang = 'pt-Br'
    domain = ['imperiodabritannia.com']

    def __init__(self):
        self.url = 'https://imperiodabritannia.com/'

        self.path = ''
        
        self.query_mangas = 'div.page-item-detail.manga a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        ua = UserAgent()
        user = ua.chrome
        self.user = ua.chrome
        self.headers = {'host': 'imperiodabritannia.com', 'User-Agent': user, 'referer': f'{self.url}', 'Cookie': 'acesso_legitimo=1'}

    def getManga(self, link: str) -> Manga:
        response = Http.get(link, timeout=getattr(self, 'timeout', None))

        if not response or not getattr(response, "text", None):
            raise Exception(f"Falha ao acessar {link} - status: {getattr(response, 'status_code', '??')}")

        soup = BeautifulSoup(response.content, "html.parser")

        data = soup.select(self.query_title_for_uri)
        if not data:
            print(f"[DEBUG] Nenhum elemento encontrado com selector '{self.query_title_for_uri}'")
            print(f"[DEBUG] HTML retornado (primeiros 300 chars):\n{response.text[:300]}...")
            raise Exception("Não foi possível extrair o título do mangá")

        element = data.pop()
        title = element.get("content", "").strip() or element.text.strip()

        if not title:
            raise Exception("Título vazio ou não encontrado")

        return Manga(id=link, name=title)

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
            ch_number = el.text.strip()
            ch_name = title
            chs.append(Chapter(ch_id, ch_number, ch_name))

        chs.reverse()
        return chs

    def getPages(self, ch: Chapter) -> Pages:
        uri = urljoin(self.url, ch.id)
        uri = self._add_query_params(uri, {'style': 'list'})
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        data = soup.select(self.query_pages)
        if not data:
            uri = self._remove_query_params(uri, ['style'])
            response = Http.get(uri, timeout=getattr(self, 'timeout', None))
            soup = BeautifulSoup(response.content, 'html.parser')
            data = soup.select(self.query_pages)
        list = [] 
        for el in data:
            list.append(self._process_page_element(el, uri))
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        return Pages(ch.id, number, ch.name, list)


    def _get_chapters_ajax(self, manga_id):
        uri = urljoin(self.url, f'{manga_id}ajax/chapters/?t=1')
        response = Http.post(uri, headers = {
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.8",
            "content-length": "0",
            "origin": "https://imperiodabritannia.com",
            "priority": "u=1, i",
            "referer": "https://imperiodabritannia.com/manga/flagelo-do-homem/",
            "sec-ch-ua": '"Not;A=Brand";v="99", "Brave";v="139", "Chromium";v="139"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version-list": '"Not;A=Brand";v="99.0.0.0", "Brave";v="139.0.0.0", "Chromium";v="139.0.0.0"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": '"19.0.0"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
            "cookie": "__stripe_mid=9d947829-11ca-4f5d-a20b-5a3dceabb1a4832f99; lp_678484=https://imperiodabritannia.com/; ezovuuid_678484=7fd3d193-dc1c-49ba-721c-e81551baab75; ezoref_678484=imperiodabritannia.com; __stripe_sid=c63211ac-04d5-40d9-a7a0-89c66fbca6d2faf392; cf_clearance=BARHNLrKUavDT0.VpN9zcpN7FR5whz4KCPaW1M3hoBw-1756513598-1.2.1.1-JtHHyLsAjiE.6z43rrh_H6yB3bXyt.xmBswvopmc4h.wNxf..39ISZJx058JomhEdVLgsyLvN0qsgZYmfuAh.l_TDOMY30A6jTtBnG0aJfV1GJP45yE0ysYKo3.a1qFM3TOPXBacl8ZEQyNiRiBg0Az3AN.6uZPVYgAYoiwyafAMnHiyNw9_BxxmCOZAJqp6MGenreKK_uIfURwAHUuEwWUAlgAEdTQfQyU4IPfcYy.l_8RXnW.zrtjt4SGoKS17; ezoab_678484=mod126-c; ezosuibasgeneris-1=ee59a4bd-7e89-4362-42f5-4b4af3645b2e; ezoictest=stable; ezopvc_678484=4; ezovuuidtime_678484=1756514126; ezds=ffid%3D1%2Cw%3D1680%2Ch%3D1050; ezohw=w%3D983%2Ch%3D917"
})
        data = self._fetch_dom(response, self.query_chapters)
        if data:
            return data
        else:
            raise Exception('No chapters found (new ajax endpoint)!')
