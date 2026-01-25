from core.providers.infra.template.base import Base
import re
import json
from urllib.parse import parse_qs, urlparse
from typing import List
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga

class HospicioProvider(Base):
    name = 'Hospício'
    lang = 'pt-Br'
    domain = ['hospicio.base44.app']
    
    def __init__(self):
        self.url = 'https://hospicio.base44.app/'
        self.api_url = 'https://base44.app/api/apps/6937632b7938da3d84abfba0/entities'
        self.app_id = '6937632b7938da3d84abfba0'
        self.bearer_token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJpbnNhbmFtZW50ZWVueWdtYXRpY29AZ21haWwuY29tIiwiZXhwIjoxNzc3MDQ4NzM2LCJpYXQiOjE3NjkyNzI3MzZ9.AgjbP9Txge4dpPyqMe-7rGSgN6WG7WCoCYRsN3W-GrQ'
    
    def _get_headers(self, origin_url=None):
        """Retorna headers padrão para requisições à API"""
        headers = {
            'accept': 'application/json',
            'accept-language': 'pt-BR,pt;q=0.5',
            'authorization': f'Bearer {self.bearer_token}',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'x-app-id': self.app_id
        }
        if origin_url:
            headers['x-origin-url'] = origin_url
        return headers
    
    def _extract_id_from_url(self, url: str) -> str:
        """Extrai o ID da obra da URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get('id', [''])[0]
    
    def getManga(self, link: str) -> Manga:
        """Obtém informações da obra"""
        obra_id = self._extract_id_from_url(link)
        
        query = json.dumps({"id": obra_id})
        api_url = f"{self.api_url}/Obra?q={query}"
        
        headers = self._get_headers(link)
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        if not data or len(data) == 0:
            raise Exception(f"Obra não encontrada: {obra_id}")
        
        obra = data[0]
        title = obra.get('titulo', 'Título Desconhecido')
        
        return Manga(id=obra_id, name=title)
    
    def getChapters(self, id: str) -> List[Chapter]:
        """Obtém lista de capítulos da obra"""
        query = json.dumps({"obra_id": id, "status": "ativo"})
        api_url = f"{self.api_url}/Chapter?q={query}&sort=numero"
        
        origin_url = f"{self.url}obradetalhes?id={id}"
        headers = self._get_headers(origin_url)
        
        response = Http.get(api_url, headers=headers)
        data = response.json()
        
        chapters = []
        for ch in data:
            ch_id = ch.get('id', '')
            ch_number = ch.get('numero', 0)
            ch_title = ch.get('titulo', '') or ch.get('obra_titulo', '')
            
            # Cria um objeto Chapter com ID único
            chapters.append(Chapter(
                id=ch_id,
                number=str(ch_number),
                name=ch_title
            ))
        
        return chapters
    
    def getPages(self, ch: Chapter) -> Pages:
        """Obtém as páginas/imagens do capítulo"""
        # Busca o capítulo específico pela API para obter as imagens
        api_url = f"{self.api_url}/Chapter?q={json.dumps({'id': ch.id})}"
        
        headers = self._get_headers()
        response = Http.get(api_url, headers=headers)
        
        data = response.json()
        if not data or len(data) == 0:
            raise Exception(f"Capítulo não encontrado: {ch.id}")
        
        chapter_data = data[0]
        images = chapter_data.get('imagens', [])
        
        number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
        
        return Pages(ch.id, number, ch.name, images)
