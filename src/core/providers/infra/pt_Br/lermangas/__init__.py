from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.download.application.use_cases import DownloadUseCase
from core.providers.domain.entities import Chapter, Pages, Manga

class LerMangasProvider(WordPressMadara):
    name = 'Ler mangas'
    lang = 'pt-Br'
    domain = ['lermangas.me']

    def __init__(self):
        self.url = 'https://lermangas.me'

        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        
        # Headers necessários para download de imagens do CDN (lercdn3.azmanga.net)
        self.image_headers = {
            'sec-ch-ua': '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'referer': 'https://lermangas.me/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36'
        }
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        # Usa os headers customizados para imagens se nenhum header foi fornecido
        if headers is None:
            headers = self.image_headers
        return DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)