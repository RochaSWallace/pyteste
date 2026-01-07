import re
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin

class CapitoonsProvider(Base):
    name = 'Capitoons'
    lang = 'pt-Br'
    domain = ['capitoons.com']
    has_login = False

    def __init__(self):
        self.url = 'https://capitoons.com'
        self.query_title = 'h1.text-4xl.font-bold.mb-2'
        self.query_chapter_list = '#chapter_list[data-post-id]'
        self.query_chapter_links = 'li a[href*="capitulo"]'
        self.query_chapter_number = 'span.m-0'
        self.query_next_button = 'button.load-chapters'
        self.query_images = 'div.reader-area img#imagech[src]'

    def getManga(self, link: str) -> Manga:
        """Obtém informações do manga"""
        response = Http.get(link)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_tag = soup.select_one(self.query_title)
        title = title_tag.get_text(strip=True) if title_tag else 'Unknown'
        
        return Manga(id=link, name=title)

    def getChapters(self, id: str) -> List[Chapter]:
        """Obtém lista de capítulos usando requisição AJAX"""
        response = Http.get(id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Obtém o título do manga
        title_tag = soup.select_one(self.query_title)
        title = title_tag.get_text(strip=True) if title_tag else 'Unknown'
        
        # Busca o post_id no atributo data-post-id
        chapter_list = soup.select_one(self.query_chapter_list)
        if not chapter_list or 'data-post-id' not in chapter_list.attrs:
            return []
        
        post_id = chapter_list['data-post-id']
        
        # Faz requisições AJAX para obter todos os capítulos
        # Começa com ordem ASC para pegar os últimos capítulos
        chapters = []
        
        # Primeiro, busca com ordem ASC (capítulos mais recentes)
        for order in ['ASC', 'DESC']:
            paged = 1
            while True:
                # Monta o body application/x-www-form-urlencoded
                body = f'action=load_chapters&post_id={post_id}&count=1000&paged={paged}&order={order}'
            
                headers = {
                    'content-type': 'application/x-www-form-urlencoded',
                    'referer': id
                }
                
                ajax_url = urljoin(self.url, '/wp-admin/admin-ajax.php')
                ajax_response = Http.post(ajax_url, data=body, headers=headers)
                
                # Parse da resposta HTML
                ajax_soup = BeautifulSoup(ajax_response.content, 'html.parser')
                
                # Busca os links dos capítulos
                chapter_links = ajax_soup.select(self.query_chapter_links)
                
                if not chapter_links:
                    break
                
                for link in chapter_links:
                    href = link.get('href')
                    if not href:
                        continue
                    
                    # Evita duplicados
                    if any(ch.id == href for ch in chapters):
                        continue
                    
                    # Extrai o número do capítulo
                    number_span = link.select_one(self.query_chapter_number)
                    if number_span:
                        number_text = number_span.get_text(strip=True)
                        # Remove "Capítulo " do texto
                        number = re.sub(r'Capítulo\s*', '', number_text, flags=re.IGNORECASE).strip()
                    else:
                        # Tenta extrair do href
                        match = re.search(r'capitulo[- ](\d+(?:\.\d+)?)', href, re.IGNORECASE)
                        number = match.group(1) if match else str(len(chapters) + 1)
                    
                    chapters.append(Chapter(id=href, number=number, name=title))
                
                # Verifica se há botão "Próximo" para continuar
                next_button = ajax_soup.select_one('button.load-chapters')
                if next_button and 'data-paged' in next_button.attrs:
                    next_paged = next_button['data-paged']
                    if next_paged and int(next_paged) > paged:
                        paged = int(next_paged)
                    else:
                        break
                else:
                    break
        
        # Ordena por número do capítulo
        chapters.sort(key=lambda ch: float(re.findall(r'\d+\.?\d*', str(ch.number))[0]) if re.findall(r'\d+\.?\d*', str(ch.number)) else 0)
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        """Obtém as páginas de um capítulo"""
        response = Http.get(ch.id)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        pages = []
        
        # Busca especificamente na div.reader-area
        reader_area = soup.select_one('div.reader-area')
        if reader_area:
            img_tags = reader_area.select('img#imagech[src]')
            for img in img_tags:
                src = img.get('src')
                if src and src not in pages:
                    pages.append(src)
        
        # Se não encontrou, tenta buscar em outros containers
        if not pages:
            img_tags = soup.select('img[src]')
            for img in img_tags:
                src = img.get('data-src') or img.get('src')
                if src and 'wp-content/uploads' in src:
                    if 'logo' not in src.lower() and src not in pages:
                        pages.append(src)
        
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
        return Pages(id=ch.id, number=number, name=ch.name, pages=pages)
