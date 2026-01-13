from core.providers.infra.template.wordpress_madara import WordPressMadara
import re
import json
import requests
import base64
import hashlib
from typing import List, Any, Dict
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qs


class NexusToonsDecryptor:
    """Desencripta respostas da API NexusToons"""
    
    SECRET_KEY = "OrionNexus2025CryptoKey!Secure"
    
    def __init__(self):
        self.keys = []
        self.initialized = False
        self._init_from_secret()
    
    def _init_from_secret(self):
        """Gera as 5 chaves a partir da chave secreta"""
        keys = []
        for i in range(5):
            # Gera a string para hash
            key_str = f"_orion_key_{i}_v2_{self.SECRET_KEY}"
            
            # Calcula SHA-256
            sha256_hash = hashlib.sha256(key_str.encode()).digest()
            
            # Converte para hex string
            hex_key = sha256_hash.hex()
            keys.append(hex_key)
        
        self._init_keys(keys)
    
    def _init_keys(self, keys: List[str]):
        """Inicializa as chaves e S-Boxes"""
        if len(keys) != 5:
            raise ValueError("São necessárias exatamente 5 chaves")
        
        self.keys = []
        for key_hex in keys:
            # Converte hex para bytes
            key_bytes = bytes.fromhex(key_hex)
            
            # Cria S-Box e S-Box reversa
            sbox = list(range(256))
            rsbox = [0] * 256
            
            # Inicializa S-Box
            j = 0
            for i in range(256):
                j = (j + sbox[i] + key_bytes[i % len(key_bytes)]) % 256
                sbox[i], sbox[j] = sbox[j], sbox[i]
            
            # Cria S-Box reversa
            for i in range(256):
                rsbox[sbox[i]] = i
            
            self.keys.append({
                'key': key_bytes,
                'sbox': sbox,
                'rsbox': rsbox
            })
        
        self.initialized = True
    
    def _rotate_right(self, byte: int, shift: int) -> int:
        """Rotaciona um byte para a direita"""
        shift = shift % 8
        return ((byte >> shift) | (byte << (8 - shift))) & 0xFF
    
    def decrypt(self, key_index: int, encrypted_b64: str) -> str:
        """Desencripta dados usando o índice da chave especificado"""
        if not self.initialized:
            raise RuntimeError("Decryptor não inicializado")
        
        if key_index < 0 or key_index >= 5:
            raise ValueError(f"Índice de chave inválido: {key_index}")
        
        # Pega a chave correspondente
        key_data = self.keys[key_index]
        key_bytes = key_data['key']
        rsbox = key_data['rsbox']
        
        try:
            # Decodifica base64
            encrypted = base64.b64decode(encrypted_b64)
        except Exception as e:
            print(f"[NexusScan] Erro ao decodificar base64: {e}")
            raise
        
        # Desencripta
        decrypted = bytearray(len(encrypted))
        key_len = len(key_bytes)
        
        for i in range(len(encrypted) - 1, -1, -1):
            byte = encrypted[i]
            
            # XOR com byte anterior (ou último byte da chave se for o primeiro)
            if i > 0:
                byte ^= encrypted[i - 1]
            else:
                byte ^= key_bytes[key_len - 1]
            
            # S-Box reversa
            byte = rsbox[byte]
            
            # Rotação reversa - CORRIGIDO: adiciona & 0xFF antes de % 7
            shift = ((key_bytes[(i + 3) % key_len] + (i & 0xFF)) & 0xFF) % 7 + 1
            byte = self._rotate_right(byte, shift)
            
            # XOR final
            byte ^= key_bytes[i % key_len]
            
            decrypted[i] = byte
        
        try:
            return decrypted.decode('utf-8')
        except UnicodeDecodeError as e:
            print(f"[NexusScan] Erro ao decodificar UTF-8: {e}")
            print(f"[NexusScan] Primeiros 50 bytes: {decrypted[:50]}")
            raise
    
    def is_encrypted_response(self, data: Any) -> bool:
        """Verifica se a resposta está encriptada"""
        if not isinstance(data, dict):
            return False
        
        return (
            isinstance(data.get('d'), str) and
            isinstance(data.get('k'), int) and
            isinstance(data.get('v'), int) and
            data.get('v') in (1, 2)
        )
    
    def process_response(self, response_data: Any) -> Any:
        """
        Processa a resposta da API, desencriptando se necessário
        """
        # Se não for encriptado, retorna como está
        if not self.is_encrypted_response(response_data):
            return response_data
        
        # Determina o índice da chave
        key_index = response_data['k'] if response_data['v'] == 2 else 0
        
        try:
            # Desencripta
            decrypted_str = self.decrypt(key_index, response_data['d'])
            
            # Parse JSON
            return json.loads(decrypted_str)
        
        except Exception as e:
            print(f"[NexusScan] Erro ao desencriptar (chave {key_index}): {e}")
            return response_data


class NexusScanProvider(WordPressMadara):
    name = 'Nexus Scan'
    lang = 'pt-Br'
    domain = ['nexustoons.com']

    def __init__(self):
        self.url = 'https://nexustoons.com/'
        self.decryptor = NexusToonsDecryptor()
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'h1.item-title'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
        self.api_chapters = 'https://nexustoons.com/api/'

    def getManga(self, link: str) -> Manga:
        """
        Obtém informações da obra via API REST
        URL da obra: https://nexustoons.com/manga/{slug}
        API: https://nexustoons.com/api/manga/{slug}
        """
        # Extrai o slug da URL
        # Exemplo: https://nexustoons.com/manga/private-tutoring-in-these-trying-times
        slug = link.rstrip('/').split('/manga/')[-1]
        
        # Chama a API
        api_url = f"https://nexustoons.com/api/manga/{slug}"
        print(f"[NexusScan] getManga API: {api_url}")
        
        try:
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            response_data = json.loads(response.content)
            
            # Desencripta a resposta se necessário
            data = self.decryptor.process_response(response_data)
            
            title = data.get('title', 'Título Desconhecido')
            print(f"[NexusScan] ✓ Obra encontrada: {title}")
            
            return Manga(id=link, name=title)
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter manga: {e}")
            raise ValueError(f"Erro ao obter informações da obra: {e}")

    def getChapters(self, id: str) -> List[Chapter]:
        """
        Obtém lista de capítulos via API REST
        A mesma API do getManga já retorna todos os capítulos
        URL dos capítulos: https://nexustoons.com/ler/{slug}/{chapter_id}
        """
        # Extrai o slug da URL
        slug = id.rstrip('/').split('/manga/')[-1]
        
        # Chama a API
        api_url = f"https://nexustoons.com/api/manga/{slug}"
        print(f"[NexusScan] getChapters API: {api_url}")
        
        try:
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            response_data = json.loads(response.content)
            
            # Desencripta a resposta se necessário
            data = self.decryptor.process_response(response_data)
            
            title = data.get('title', 'Título Desconhecido')
            chapters_data = data.get('chapters', [])
            
            if not chapters_data:
                print(f"[NexusScan] ⚠️  Nenhum capítulo encontrado para {title}")
                return []
            
            print(f"[NexusScan] ✓ {len(chapters_data)} capítulos encontrados para {title}")
            
            chs = []
            for chapter in chapters_data:
                chapter_id = chapter.get('id')
                chapter_number = str(chapter.get('number', '')).strip()
                
                if not chapter_id or not chapter_number:
                    continue
                
                # Monta a URL do capítulo: https://nexustoons.com/ler/{slug}/{chapter_id}
                ch_url = f"https://nexustoons.com/ler/{slug}/{chapter_id}"
                
                chs.append(Chapter(ch_url, chapter_number, title))
            
            # Inverte para ordem crescente (API retorna decrescente)
            chs.reverse()
            return chs
            
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter capítulos: {e}")
            raise ValueError(f"Erro ao buscar capítulos: {e}")
    
    def getPages(self, ch: Chapter) -> Pages:
        """
        Obtém páginas do capítulo via API REST
        URL do capítulo: https://nexustoons.com/ler/{slug}/{chapter_id}
        API: https://nexustoons.com/api/chapter/{chapter_id}
        """
        try:
            # Extrai o chapter_id da URL
            # Exemplo: https://nexustoons.com/ler/private-tutoring-in-these-trying-times/190265
            chapter_id = ch.id.rstrip('/').split('/')[-1]
            
            # Chama a API
            api_url = f"https://nexustoons.com/api/chapter/{chapter_id}"
            print(f"[NexusScan] getPages API: {api_url}")
            
            response = Http.get(api_url, timeout=getattr(self, 'timeout', None))
            response_data = json.loads(response.content)
            
            # Desencripta a resposta se necessário
            data = self.decryptor.process_response(response_data)
            
            # Extrai as páginas
            pages_data = data.get('pages', [])
            
            if not pages_data:
                print(f"[NexusScan] ⚠️  Nenhuma página encontrada")
                number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
                return Pages(ch.id, number, ch.name, [])
            
            # Ordena por pageNumber e extrai imageUrl
            img_urls = [page['imageUrl'] for page in sorted(pages_data, key=lambda x: x['pageNumber'])]
            
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            print(f"[NexusScan] ✓ {len(img_urls)} páginas obtidas")
            
            return Pages(ch.id, number, ch.name, img_urls)
            
        except Exception as e:
            print(f"[NexusScan] ✗ Erro ao obter páginas: {e}")
            import traceback
            traceback.print_exc()
            number = re.findall(r'\d+\.?\d*', str(ch.number))[0] if re.findall(r'\d+\.?\d*', str(ch.number)) else ch.number
            return Pages(ch.id, number, ch.name, [])
