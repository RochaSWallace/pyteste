import re
import time
import os
import math
import requests
from typing import List
from core.download.domain.dowload_entity import Chapter as DownloadedChapter
from core.config.img_conf import get_config
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.__seedwork.infra.http import Http


class GeassComicsProvider(Base):
    name = 'Geass Comics'
    lang = 'pt_Br'
    domain = ['geasscomics.xyz']
    has_login = False

    def __init__(self) -> None:
        self.url = 'https://geasscomics.xyz'
        self.api_url = 'https://api.skkyscan.fun/api'
        self.domain_key = 'geasscomics.xyz'

    def getManga(self, link: str) -> Manga:
        """Extrai informações básicas da obra via API"""
        try:
            # Extrai slug da URL
            # Formato: https://geasscomics.xyz/obra/ceifador-de-meio-periodo
            match = re.search(r'/obra/([^/]+)', link)
            if not match:
                raise Exception("Slug da obra não encontrado na URL")
            
            slug = match.group(1)
            
            print(f"[GeassComics] Acessando API da obra: {slug}")
            
            # Busca informações via API
            api_url = f"{self.api_url}/mangas/{slug}"
            
            response = Http.get(api_url)
            json_data = response.json()
            
            if not json_data.get('success'):
                raise Exception("API retornou erro")
            
            data = json_data.get('data', {})
            title = data.get('title', slug)
            manga_id = data.get('id')
            
            print(f"[GeassComics] Título: {title}")
            print(f"[GeassComics] ID: {manga_id}")
            
            # Retorna link com slug para manter compatibilidade
            return Manga(link, title)
                
        except Exception as e:
            print(f"[GeassComics] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        """Extrai todos os capítulos via API com paginação"""
        try:
            # Extrai slug da URL
            match = re.search(r'/obra/([^/]+)', manga_id)
            if not match:
                raise Exception("Slug da obra não encontrado")
            
            slug = match.group(1)
            
            # Primeiro busca o ID da manga pela API
            manga_api_url = f"{self.api_url}/mangas/{slug}"
            manga_response = Http.get(manga_api_url)
            manga_json = manga_response.json()
            
            if not manga_json.get('success'):
                raise Exception("API retornou erro ao buscar manga")
            
            manga_data = manga_json.get('data', {})
            manga_uuid = manga_data.get('id')
            manga_title = manga_data.get('title', slug)
            
            print(f"[GeassComics] Extraindo capítulos da obra: {manga_title}")  
            # Busca capítulos com paginação
            chapters_list = []
            page = 1
            limit = 100
            has_next = True
            
            while has_next:
                api_url = f"{self.api_url}/chapters?mangaId={manga_uuid}&limit={limit}&page={page}&order=asc"
                
                response = Http.get(api_url)
                json_data = response.json()
                
                if not json_data.get('success'):
                    break
                
                items = json_data.get('data', [])
                pagination = json_data.get('pagination', {})
                has_next = pagination.get('hasNext', False)
                
                if not items:
                    break
                
                # Converte para objetos Chapter
                for item in items:
                    chapter_number = item.get('chapterNumber', '0')
                    chapter_id = item.get('id')
                    chapter_title = item.get('title', f"Capítulo {chapter_number}")
                    
                    # Monta a URL do capítulo: https://geasscomics.xyz/ler/{slug}/{chapter_number}
                    # Armazena o ID do capítulo na URL para usar em getPages
                    chapter_url = f"{self.url}/ler/{slug}/{chapter_number}?id={chapter_id}"
                    
                    chapters_list.append(
                        Chapter(
                            chapter_url,
                            str(chapter_number),
                            manga_title
                        )
                    )
                
                page += 1
            
            return chapters_list
                
        except Exception as e:
            print(f"[GeassComics] Erro em getChapters: {e}")
            import traceback
            traceback.print_exc()
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai URLs das páginas de um capítulo via API"""
        try:          
            # Extrai chapter_id da URL
            # Formato: https://geasscomics.xyz/ler/{slug}/{chapter_number}?id={chapter_id}
            match = re.search(r'[?&]id=([^&]+)', ch.id)
            if not match:
                raise Exception("ID do capítulo não encontrado na URL")
            
            chapter_id = match.group(1)
            
            print(f"[GeassComics] Chapter ID: {chapter_id}")
            
            # Busca páginas via API
            # Formato: https://api.skkyscan.fun/api/chapters/{chapter_id}
            api_url = f"{self.api_url}/chapters/{chapter_id}"
            
            response = Http.get(api_url)
            json_data = response.json()
            
            if not json_data.get('success'):
                raise Exception("API retornou erro")
            
            data = json_data.get('data', {})
            pages = data.get('pages', [])
            
            if not pages:
                raise Exception("Nenhuma página encontrada")
            
            # Monta URLs completas das imagens
            # Formato: https://api.skkyscan.fun + imageUrl
            images = []
            for page in pages:
                image_url = page.get('imageUrl', '')
                # Remove a barra inicial se houver
                if image_url.startswith('/'):
                    image_url = image_url[1:]
                full_url = f"https://api.skkyscan.fun/{image_url}"
                images.append(full_url)
            
            
            return Pages(ch.id, ch.number, ch.name, images)
                
        except Exception as e:
            print(f"[GeassComics] Erro em getPages: {e}")
            import traceback
            traceback.print_exc()
            return Pages(ch.id, ch.number, ch.name, [])
