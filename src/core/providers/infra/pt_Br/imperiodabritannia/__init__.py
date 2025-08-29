from urllib.parse import urljoin
import re
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
        response = Http.post(uri, headers={'Cookie': 'visited=true; __stripe_mid=9d947829-11ca-4f5d-a20b-5a3dceabb1a4832f99; __stripe_sid=ce82d506-1c97-4e6a-9029-884358359e1a7797af; lp_678484=https://imperiodabritannia.com/; ezovuuid_678484=1b78a1fe-93a5-4010-4a6f-0ae580e82923; ezoref_678484=imperiodabritannia.com; cf_clearance=miMtdzc7bJyblo.UViiU0qqdCr_EYGLUZlaeOMmooV4-1756462072-1.2.1.1-BNv_y3CBAvw0VAW6pPpzPkoNiOtSXKlvyI2g2wCS4m_CnwmvL8ytHAwYphG1grWzTwi2KA7oughGPt.nFNMZB4b1fdBq5ZxzNh_RcAnuIDcb.RvQk3QPxMc2kk29fzqHi8q4rYPbV99dQlUmswM7YTSX.ovMG33RYQpWAzXQJwD_rsREGIuyKSjsUzvoSOZq8ykF8TmAKTU.ta1.8YuNOWZz2DRfWCI6JyVEnXN7.In7o8loZyXJD_cWmLhX8PLE; ezoictest=stable; ezoab_678484=mod126-c; ezosuibasgeneris-1=62267cc2-0ab5-41ed-4caa-e59ff6ad67d7; ezopvc_678484=3; ezovuuidtime_678484=1756462198; ezds=ffid%3D1%2Cw%3D1680%2Ch%3D1050; ezohw=w%3D1128%2Ch%3D917'})
        data = self._fetch_dom(response, self.query_chapters)
        if data:
            return data
        else:
            raise Exception('No chapters found (new ajax endpoint)!')
