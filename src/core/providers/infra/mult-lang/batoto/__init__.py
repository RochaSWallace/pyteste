import re
import json
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga

class BatotoProvider(Base):
    name = 'Batoto'
    lang = 'mult'
    domain = ['wto.to', 'bato.to', 'battwo.com', 'batotoo.com', 'xbato.net', 'xbato.com', 'bato.si', 'xcat.tv']

    def __init__(self) -> None:
        self.base = 'https://xcat.tv/'
        self.headers = {'referer': f'{self.base}'}

    def getManga(self, link: str) -> Manga:
        response = Http.get(link, headers=self.headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tenta nova estrutura: h3 > a.link-hover
        title_element = soup.select_one('h3 > a.link-hover')
        if not title_element:
            # Fallback para estrutura antiga
            title_element = soup.select_one('h3.item-title > a')
        
        if title_element:
            title_text = title_element.get_text(strip=True)
        else:
            # Último recurso: extrai do link
            title_text = link.split('/')[-1].split('-', 1)[-1].replace('-', ' ').title()
        
        result = Manga(link, title_text)
        
        # Liberar memória do BeautifulSoup
        soup.decompose()
        del soup
        
        return result

    def getChapters(self, link: str) -> List[Chapter]:
        list = []
        response = Http.get(link, headers=self.headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Nova estrutura: a.link-hover.link-primary (capítulos)
        # Nota: visited:text-accent é pseudo-classe do Tailwind, não classe CSS real
        chs = soup.select('div.group.flex.flex-col a.link-hover.link-primary')
        
        # Se não encontrou com nova estrutura, tenta a antiga
        if not chs:
            chs = soup.select('a.visited.chapt')
        
        # Tenta nova estrutura: h3 > a.link-hover
        title_element = soup.select_one('h3 > a.link-hover')
        if not title_element:
            # Fallback para estrutura antiga
            title_element = soup.select_one('h3.item-title > a')
        
        if title_element:
            title_text = title_element.get_text(strip=True)
        else:
            # Último recurso: extrai do link
            title_text = link.split('/')[-1].split('-', 1)[-1].replace('-', ' ').title()
        
        for chapter in chs:
            href = chapter.get('href')
            
            # Filtra apenas links de capítulos (ignora links de usuário /u/, etc)
            if not href or not href.startswith('/title/'):
                continue
            
            # Nova estrutura: texto direto "Chapter 26"
            chapter_text = chapter.get_text(strip=True)
            
            # Se tem <b>, usa estrutura antiga
            b_element = chapter.select_one('b')
            if b_element:
                chapter_text = b_element.get_text(strip=True)
            
            # Garante URL completa
            chapter_url = f'{self.base}{href}' if not href.startswith('http') else href
            list.append(Chapter(chapter_url, chapter_text, title_text))
        list.reverse()
        
        # Liberar memória do BeautifulSoup
        soup.decompose()
        del soup
        
        return list

    def getPages(self, ch: Chapter) -> Pages:
        list = []
        response = Http.get(ch.id, headers=self.headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script')
        
        img_https_value = None
        
        for script in scripts:
            if not script.string:
                continue
            
            # Nova estrutura: JSON Qwik
            if script.get('type') == 'qwik/json':
                try:
                    data = json.loads(script.string)
                    # As URLs das imagens estão no array "objs"
                    if 'objs' in data and type(data['objs']) == type([]):
                        # Filtra apenas URLs de imagem (começam com https://, contém /media/ e terminam com extensão de imagem)
                        for obj in data['objs']:
                            if type(obj) == type('') and obj.startswith('https://') and '/media/' in obj:
                                # Verifica se termina com extensão de imagem válida
                                if obj.lower().endswith(('.webp', '.jpg', '.jpeg', '.png', '.gif')):
                                    # Corrige URLs do servidor 'k' que podem estar com problemas
                                    # Substitui '//k' por '//n' em URLs que contêm '.mb'
                                    url = obj
                                    if '//k' in url and '.mb' in url:
                                        url = url.replace('//k', '//n')
                                    list.append(url)
                    
                    if list:
                        break
                except (json.JSONDecodeError, AttributeError, KeyError):
                    continue
            
            # Estrutura antiga: const imgHttps = [...]
            elif 'const imgHttps =' in script.string:
                match = re.search(r'const imgHttps = (\[.*?\]);', script.string, re.DOTALL)
                if match:
                    img_https_value = match.group(1)
                    break
        
        # Se usou estrutura antiga, processa o array
        if img_https_value and not list:
            try:
                img_https_list = json.loads(img_https_value)
                # Corrige URLs do servidor 'k' que podem estar com problemas
                # Substitui '//k' por '//n' em URLs que contêm '.mb'
                for url in img_https_list:
                    if url and '//k' in url and '.mb' in url:
                        url = url.replace('//k', '//n')
                    list.append(url)
            except json.JSONDecodeError:
                pass
        
        return Pages(ch.id, ch.number, ch.name, list)

