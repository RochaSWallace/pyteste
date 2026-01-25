from core.providers.infra.template.base import Base
import re
from urllib.parse import parse_qs, urlparse
from typing import List
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga

class WolftoonProvider(Base):
    name = 'WolfToon'
    lang = 'pt-Br'
    domain = ['wolftoon.lovable.app']
    
    def __init__(self):
        self.url = 'https://wolftoon.lovable.app/'
        self.api_url = 'https://encmakrlmutvsdzpodov.supabase.co/rest/v1'
        self.apikey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVuY21ha3JsbXV0dnNkenBvZG92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQ3MjUzMjUsImV4cCI6MjA4MDMwMTMyNX0.pBNvagvrtZeu4VubAJbhSCXZBsI0trxpMJJDFrKw_Kk'
        self.headers = {
            'accept': 'application/json',
            'accept-profile': 'public',
            'apikey': self.apikey,
            'authorization': f'Bearer {self.apikey}',
            'Referer': self.url
        }
    
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
        
        api_url = f"{self.api_url}/titles?select=*&id=eq.{title_id}"
        
        headers = {**self.headers, 'accept': 'application/vnd.pgrst.object+json'}
        
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        if not data:
            raise Exception(f"Obra não encontrada: {title_id}")
        
        title = data.get('title', 'Título Desconhecido')
        
        return Manga(id=title_id, name=title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        """Obtém lista de capítulos da obra"""
        api_url = f"{self.api_url}/chapters?select=*&title_id=eq.{id}&order=chapter_number.desc"
        
        response = Http.get(api_url, headers=self.headers)
        
        data = response.json()
        
        chapters = []
        for ch in data:
            ch_id = ch.get('id', '')
            ch_number = ch.get('chapter_number', 0)
            ch_title = ch.get('chapter_title', '')
            
            # Se não tem título, busca o título da obra
            if not ch_title:
                # Aqui poderia fazer outra requisição para pegar o título da obra
                # Mas vamos deixar vazio por enquanto
                ch_title = ''
            
            chapters.append(Chapter(
                id=ch_id,
                number=str(ch_number),
                name=ch_title
            ))
        
        return chapters
    
    def getPages(self, ch: Chapter) -> Pages:
        """Obtém as páginas/imagens do capítulo"""
        # Busca o capítulo específico pela API para obter as imagens
        api_url = f"{self.api_url}/chapters?select=*&id=eq.{ch.id}"
        
        headers = {**self.headers, 'accept': 'application/vnd.pgrst.object+json'}
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        if not data:
            raise Exception(f"Capítulo não encontrado: {ch.id}")
        
        images = data.get('images', [])
        
        # Extrai apenas números do chapter number
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
        
        return Pages(ch.id, number, ch.name, images)
