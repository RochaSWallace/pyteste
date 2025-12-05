from typing import List
from core.__seedwork.infra.http import Http
from bs4 import BeautifulSoup
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

class NorusProvider(Base):
    name = 'Norus'
    lang = 'pt_Br'
    domain = ['beta.norus.site']

    def __init__(self):
        self.url = 'https://beta.norus.site'
        self.link = 'https://beta.norus.site/'
        # Seletores CSS - ajuste conforme a estrutura do site
        self.get_title = 'h1'
        self.get_chapters_list = 'div.space-y-2'
        self.chapter = 'a'
        self.get_chapter_name = 'span.text-white.font-medium'
        self.get_div_page = 'div.reading-content'
        self.get_pages = 'img'

    def getManga(self, link: str) -> Manga:
        """Extrai informações do mangá"""
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar título
        title_element = soup.select_one(self.get_title)
        if title_element:
            title = title_element.get_text().strip()
        else:
            # Fallback: buscar em meta tags
            meta_title = soup.find('meta', property='og:title')
            title = meta_title['content'] if meta_title else 'Título Desconhecido'
        
        print(f"[Norus] Mangá encontrado: {title}")
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        """Extrai lista de capítulos"""
        list = []
        
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar título do mangá
        title_element = soup.select_one(self.get_title)
        manga_title = title_element.get_text().strip() if title_element else 'Título Desconhecido'
        
        # Buscar container de capítulos
        chapters_container = soup.select_one(self.get_chapters_list)
        
        if not chapters_container:
            print(f"[Norus] Container {self.get_chapters_list} não encontrado")
            # Tentar seletor alternativo
            chapters_container = soup.select_one('ul.chapter-list, div.chapters-list, div.page-content-listing')
            
            if not chapters_container:
                print("[Norus] Nenhum container de capítulos encontrado")
                return list
        
        # Buscar todos os links de capítulos
        chapter_links = chapters_container.select(self.chapter)
        
        if not chapter_links:
            # Tentar seletores alternativos
            chapter_links = chapters_container.select('a[href*="capitulo"], a[href*="chapter"], li a')
        
        print(f"[Norus] Encontrados {len(chapter_links)} capítulos")
        
        for ch_link in chapter_links:
            chapter_url = ch_link.get('href')
            
            if not chapter_url:
                continue
            
            # Extrair nome do capítulo usando o seletor específico
            name_elem = ch_link.select_one(self.get_chapter_name)
            if name_elem:
                chapter_name = name_elem.get_text().strip()
            else:
                # Fallback: tentar pegar texto direto (pode incluir dados extras)
                chapter_name = ch_link.get_text().strip() or 'Capítulo'
            
            # Garantir URL completa
            if not chapter_url.startswith('http'):
                chapter_url = f"{self.url}{chapter_url}" if chapter_url.startswith('/') else f"{self.url}/{chapter_url}"
            
            chapter_obj = Chapter(
                chapter_url,
                chapter_name,
                manga_title
            )
            list.append(chapter_obj)
        
        return list

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai páginas/imagens do capítulo via API"""
        # Extrair o UUID do capítulo da URL
        # ch.id exemplo: https://beta.norus.site/chapters/e7d7d93d-0b8f-4a2e-9acb-ad96f627cb38
        chapter_uuid = ch.id.split('/chapters/')[-1]
        
        # Construir URL da API
        api_url = f"https://api.norus.site/api/v1/chapters/{chapter_uuid}/images"
        
        try:
            response = Http.get(api_url)
            data = response.json()
            
            if data.get('success') and 'data' in data and 'images' in data['data']:
                images = data['data']['images']
                # Extrair URLs ordenadas por página
                image_urls = [img['url'] for img in sorted(images, key=lambda x: x['page'])]
                
                print(f"[Norus] Encontradas {len(image_urls)} páginas via API")
                return Pages(ch.id, ch.number, ch.name, image_urls)
            else:
                print(f"[Norus] API retornou resposta inválida: {data}")
                return Pages(ch.id, ch.number, ch.name, [])
                
        except Exception as e:
            print(f"[Norus] Erro ao buscar imagens da API: {e}")
            return Pages(ch.id, ch.number, ch.name, [])
