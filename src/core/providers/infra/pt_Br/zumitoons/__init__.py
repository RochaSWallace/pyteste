from core.providers.infra.template.base import Base
import re
from urllib.parse import parse_qs, urlparse
from typing import List
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga

class ZumiToonsProvider(Base):
    name = 'ZumiToons'
    lang = 'pt-Br'
    domain = ['zumitoons.com']
    
    def __init__(self):
        self.url = 'https://zumitoons.com/'
        self.api_url = 'https://vbnlckfypsmnvwlsavqd.supabase.co/rest/v1'
        self.apikey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZibmxja2Z5cHNtbnZ3bHNhdnFkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1ODk2OTIsImV4cCI6MjA4NDE2NTY5Mn0.Gq_yoJv7r18UA3yOK_0b5OM4-skEYnWbvnwxkLcwpj8'
        self.headers = {
            'accept': 'application/json',
            'accept-language': 'pt-BR,pt;q=0.8',
            'accept-profile': 'public',
            'apikey': self.apikey,
            'authorization': f'Bearer {self.apikey}',
            'x-client-info': 'supabase-js-web/2.90.1',
            'Referer': self.url
        }
        # Cache de páginas para evitar requisições desnecessárias
        self._pages_cache = {}
    
    def _extract_id_from_url(self, url: str) -> str:
        """Extrai o ID da obra da URL"""
        parsed = urlparse(url)
        # URL pode ser /manga/{id}, /title/{id} ou ?id={id}
        if '/manga/' in url:
            return url.split('/manga/')[-1].split('?')[0].split('/')[0]
        elif '/title/' in url:
            return url.split('/title/')[-1].split('?')[0].split('/')[0]
        
        params = parse_qs(parsed.query)
        return params.get('id', [''])[0]
    
    def getManga(self, link: str) -> Manga:
        """Obtém informações da obra"""
        title_id = self._extract_id_from_url(link)
        
        api_url = f"{self.api_url}/mangas?select=*&id=eq.{title_id}"
        
        headers = {**self.headers}
        
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        if not data:
            raise Exception(f"Obra não encontrada: {title_id}")
        
        # Se retornar lista, pega o primeiro item
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        
        title = data.get('title', 'Título Desconhecido')
        
        return Manga(id=title_id, name=title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        """Obtém lista de capítulos da obra"""
        api_url_title = f"{self.api_url}/mangas?select=*&id=eq.{id}"
        headers = {**self.headers}
        response_title = Http.get(api_url_title, headers=headers)
        data_title = response_title.json()
        if not data_title:
            raise Exception(f"Obra não encontrada: {title_id}")
        
        # Se retornar lista, pega o primeiro item
        if isinstance(data_title, list) and len(data_title) > 0:
            data_title = data_title[0]
        
        title = data_title.get('title', 'Título Desconhecido')
        
        
        api_url = f"{self.api_url}/chapters?select=*&manga_id=eq.{id}&order=chapter_number.asc&offset=0&limit=1000"
        
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        
        chapters = []
        for ch in data:
            ch_id = ch.get('id', '')
            ch_number = ch.get('chapter_number', 0)
            
            # Armazena as páginas em cache para uso posterior
            pages = ch.get('pages', [])
            if pages:
                self._pages_cache[ch_id] = pages
            
            chapters.append(Chapter(
                id=ch_id,
                number=str(ch_number),
                name=title
            ))
        
        return chapters
    
    def getPages(self, ch: Chapter) -> Pages:
        """Obtém as páginas/imagens do capítulo"""
        # Tenta buscar do cache primeiro
        images = self._pages_cache.get(ch.id)
        
        # Se não estiver em cache, busca da API
        if images is None:
            api_url = f"{self.api_url}/chapters?select=*&id=eq.{ch.id}"
            headers = {**self.headers}
            response = Http.get(api_url, headers=headers)
            
            data = response.json()
            if not data:
                raise Exception(f"Capítulo não encontrado: {ch.id}")
            
            # Se retornar lista, pega o primeiro item
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            
            images = data.get('pages', [])
        
        # Extrai apenas números do chapter number
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
        
        return Pages(ch.id, number, ch.name, images)
