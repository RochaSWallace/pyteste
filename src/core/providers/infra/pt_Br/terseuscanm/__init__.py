from core.providers.infra.template.blogger_cms import BloggerCms
from typing import List
from urllib.parse import quote
import json
import re
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
import selectolax
from core.providers.domain.entities import Chapter, Pages, Manga

class TerseuScanMProvider(BloggerCms):
    name = 'Terseu Scan M'
    lang = 'pt-Br'
    domain = ['terseuscanm.blogspot.com']
    has_login = False

    def __init__(self):
        self.get_title = 'h1#post-title'
        self.API_domain = 'terseuscanm.blogspot.com'
        self.get_pages = 'div.separator a img'

    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)

        return Manga(link, title.get_text(strip=True))

    def getChapters(self, id: str) -> List[Chapter]:
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.select_one(self.get_title)
        
        # Extrai o título original do atributo data-labelchapter
        chapter_get_div = soup.select_one('div.chapter_get')
        original_title = chapter_get_div.get('data-labelchapter') if chapter_get_div else title.get_text(strip=True)
        
        # Encode do título original para a URL
        encoded_title = quote(original_title)

        # Headers personalizados para a requisição
        headers = {
            'accept': '*/*',
            'accept-language': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'priority': 'u=1, i',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'referer': id
        }
        
        # URL com alt=json-in-script e orderby=updated (JSONP)
        api_url = f'https://{self.API_domain}/feeds/posts/default/-/{encoded_title}?alt=json-in-script&start-index=1&max-results=150&orderby=updated'
        response = Http.get(api_url, headers=headers)
        
        # Decodifica o conteúdo da resposta
        jsonp_text = response.content.decode('utf-8') if isinstance(response.content, bytes) else str(response.content)
        
        # Extrai o JSON de dentro da função callback JSONP
        json_match = re.search(r'gdata\.io\.handleScriptLoaded\((.*)\);?$', jsonp_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            data = json.loads(json_str)
        else:
            # Fallback: tenta parsear como JSON direto
            data = response.json() if callable(getattr(response, 'json', None)) else response.json
        
        chapters = []
        for ch in data['feed']['entry']:
            # Procura o link do tipo 'alternate'
            chapter_link = None
            for link in ch['link']:
                if link.get('rel') == 'alternate' and link.get('type') == 'text/html':
                    chapter_link = link['href']
                    break
            
            # Pula se for a mesma página ou se não encontrou link
            if not chapter_link or chapter_link == id:
                continue
                
            chapters.append(Chapter(chapter_link, ch['title']['$t'], title.get_text(strip=True)))
        
        return chapters
     