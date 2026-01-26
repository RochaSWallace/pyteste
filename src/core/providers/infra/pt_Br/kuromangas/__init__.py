import re
import json
import requests
from typing import List
from datetime import datetime
import hashlib
import struct
import base64

from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.config.login_data import insert_login, LoginData, get_login


def _decrypt_rabbit_cipher(encrypted_b64: str, key: str) -> dict:
    """
    Descriptografa dados no formato CryptoJS Rabbit (implementação Python pura)
    
    Args:
        encrypted_b64: String criptografada em base64 (formato CryptoJS)
        key: Chave de descriptografia (string)
        
    Returns:
        Dicionário com dados descriptografados
    """
    try:
        # Decodifica base64
        encrypted_data = base64.b64decode(encrypted_b64)
        
        # Formato CryptoJS: "Salted__" + salt (8 bytes) + ciphertext
        if encrypted_data[:8] == b'Salted__':
            salt = encrypted_data[8:16]
            ciphertext = encrypted_data[16:]
            
            # Deriva chave e IV usando MD5 (mesmo que CryptoJS)
            key_bytes = key.encode('utf-8')
            key_material = hashlib.md5(key_bytes + salt).digest()
            iv_material = hashlib.md5(key_material + key_bytes + salt).digest()
            
            derived_key = key_material  # 16 bytes
            derived_iv = iv_material[:8]  # 8 bytes
        else:
            # Sem salt - usa chave diretamente
            ciphertext = encrypted_data
            derived_key = key.encode('utf-8')
            derived_iv = None
        
        # Descriptografa usando Rabbit
        decrypted = _rabbit_decrypt(ciphertext, derived_key, derived_iv)
        
        # Remove padding PKCS7
        if len(decrypted) > 0:
            padding_length = decrypted[-1]
            if padding_length <= 16:
                decrypted = decrypted[:-padding_length]
        
        # Decodifica UTF-8 e parseia JSON
        decrypted_str = decrypted.decode('utf-8', errors='ignore')
        return json.loads(decrypted_str)
        
    except Exception as e:
        print(f"[Rabbit] ❌ Erro ao descriptografar: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _rabbit_decrypt(ciphertext: bytes, key: bytes, iv: bytes = None) -> bytes:
    """Implementação simplificada do Rabbit cipher para descriptografia"""
    
    # Garante que a chave tenha 16 bytes
    if len(key) < 16:
        key = key.ljust(16, b'\x00')
    elif len(key) > 16:
        key = hashlib.md5(key).digest()
    
    # Estado interno
    X = [0] * 8
    C = [0] * 8
    b = 0
    
    # Converte chave para lista de 32-bit words
    k = list(struct.unpack('<4I', key[:16]))
    
    # Inicialização do estado
    for i in range(8):
        if i % 2 == 0:
            X[i] = (k[i % 4] << 16) | (k[(i + 1) % 4] & 0xFFFF)
            C[i] = (k[(i + 2) % 4] << 16) | (k[(i + 3) % 4] & 0xFFFF)
        else:
            X[i] = (k[(i + 1) % 4] << 16) | (k[(i + 2) % 4] & 0xFFFF)
            C[i] = (k[(i + 3) % 4] << 16) | (k[i % 4] & 0xFFFF)
    
    # Função auxiliar para rotação
    def rotl(val: int, n: int) -> int:
        val &= 0xFFFFFFFF
        return ((val << n) | (val >> (32 - n))) & 0xFFFFFFFF
    
    # Função para avançar o estado
    def next_state():
        nonlocal b
        C_old = C[:]
        
        C[0] = (C[0] + 0x4D34D34D + b) & 0xFFFFFFFF
        C[1] = (C[1] + 0xD34D34D3 + (1 if C[0] < C_old[0] else 0)) & 0xFFFFFFFF
        C[2] = (C[2] + 0x34D34D34 + (1 if C[1] < C_old[1] else 0)) & 0xFFFFFFFF
        C[3] = (C[3] + 0x4D34D34D + (1 if C[2] < C_old[2] else 0)) & 0xFFFFFFFF
        C[4] = (C[4] + 0xD34D34D3 + (1 if C[3] < C_old[3] else 0)) & 0xFFFFFFFF
        C[5] = (C[5] + 0x34D34D34 + (1 if C[4] < C_old[4] else 0)) & 0xFFFFFFFF
        C[6] = (C[6] + 0x4D34D34D + (1 if C[5] < C_old[5] else 0)) & 0xFFFFFFFF
        C[7] = (C[7] + 0xD34D34D3 + (1 if C[6] < C_old[6] else 0)) & 0xFFFFFFFF
        
        b = 1 if C[7] < C_old[7] else 0
        
        # Função G
        G = [0] * 8
        for i in range(8):
            t = (X[i] + C[i]) & 0xFFFFFFFF
            t_sq = (t * t) & 0xFFFFFFFFFFFFFFFF
            G[i] = (t_sq ^ (t_sq >> 32)) & 0xFFFFFFFF
        
        # Atualiza estado X
        X[0] = (G[0] + rotl(G[7], 16) + rotl(G[6], 16)) & 0xFFFFFFFF
        X[1] = (G[1] + rotl(G[0], 8) + G[7]) & 0xFFFFFFFF
        X[2] = (G[2] + rotl(G[1], 16) + rotl(G[0], 16)) & 0xFFFFFFFF
        X[3] = (G[3] + rotl(G[2], 8) + G[1]) & 0xFFFFFFFF
        X[4] = (G[4] + rotl(G[3], 16) + rotl(G[2], 16)) & 0xFFFFFFFF
        X[5] = (G[5] + rotl(G[4], 8) + G[3]) & 0xFFFFFFFF
        X[6] = (G[6] + rotl(G[5], 16) + rotl(G[4], 16)) & 0xFFFFFFFF
        X[7] = (G[7] + rotl(G[6], 8) + G[5]) & 0xFFFFFFFF
    
    # Iterações de setup
    for _ in range(4):
        next_state()
    
    # Reinicializa contadores
    for i in range(8):
        C[i] ^= X[(i + 4) % 8]
    
    # Aplica IV se fornecido
    if iv is not None:
        if len(iv) < 8:
            iv = iv.ljust(8, b'\x00')
        
        iv_words = list(struct.unpack('<2I', iv[:8]))
        
        C[0] ^= iv_words[0]
        C[1] ^= ((iv_words[1] & 0xFFFF0000) | (iv_words[0] & 0xFFFF))
        C[2] ^= iv_words[1]
        C[3] ^= ((iv_words[0] & 0xFFFF0000) | (iv_words[1] & 0xFFFF))
        C[4] ^= iv_words[0]
        C[5] ^= ((iv_words[1] & 0xFFFF0000) | (iv_words[0] & 0xFFFF))
        C[6] ^= iv_words[1]
        C[7] ^= ((iv_words[0] & 0xFFFF0000) | (iv_words[1] & 0xFFFF))
        
        for _ in range(4):
            next_state()
    
    # Função para extrair keystream
    def extract() -> bytes:
        next_state()
        
        S = [
            (X[0] ^ (X[5] >> 16) ^ (X[3] << 16)) & 0xFFFFFFFF,
            (X[2] ^ (X[7] >> 16) ^ (X[5] << 16)) & 0xFFFFFFFF,
            (X[4] ^ (X[1] >> 16) ^ (X[7] << 16)) & 0xFFFFFFFF,
            (X[6] ^ (X[3] >> 16) ^ (X[1] << 16)) & 0xFFFFFFFF
        ]
        
        return struct.pack('<4I', *S)
    
    # Descriptografa
    result = bytearray()
    for i in range(0, len(ciphertext), 16):
        keystream = extract()
        block = ciphertext[i:i+16]
        
        for j in range(len(block)):
            result.append(block[j] ^ keystream[j])
    
    return bytes(result)


class KuromangasProvider(Base):
    name = 'Kuromangas'
    lang = 'pt_Br'
    domain = ['beta.kuromangas.com']
    has_login = True

    def __init__(self) -> None:
        self.base = 'https://beta.kuromangas.com'
        self.api_base = 'https://beta.kuromangas.com/api'
        self.cdn = 'https://cdn.kuromangas.com'
        self.domain_name = 'beta.kuromangas.com'
        self.access_token = None
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "pt-BR,pt;q=0.7",
            "content-type": "application/json",
            "sec-ch-ua": '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "referer": self.base
        }
        # Carrega token salvo se existir
        self._load_token()
    
    def _gerar_chave_descriptografia(self) -> str:
        """
        Gera a chave de descriptografia dinâmica do KuroMangas
        Baseado em: string_fixa + MD5(data_atual + hostname::v2 + identificador_ambiente)[:8]
        
        Nova lógica (v9.7):
        - Base: "53tou8lsakybsasjsksjdfE2oMwkkajkun9TuYTuP6dsWIF4jeKdqEwhUEft9787910"
        - Data: formato ISO (YYYY-MM-DD)
        - Hostname: "beta.kuromangas.com::v2"
        - Identificador: "x9_4v2_b" (ambiente web normal)
        - Hash: MD5(data + hostname + identificador)[:8]
        """
        # String base fixa (atualizada)
        base_key = "53to8lsakybskhjk6sjsksjdfE2oMwkajkun9TuYTuP6dsWIF4jeKdqEwhUEft9787910"
        
        # Data atual no formato ISO (YYYY-MM-DD)
        data_atual = datetime.now().strftime("%Y-%m-%d")
        
        # Hostname com sufixo ::v2
        hostname_v2 = "beta.kuromangas.com::v2"
        
        # Identificador do ambiente
        # window.KuroInterface || window.Android ? "poisoned_webview" : 
        # window.getComputedStyle && window.getComputedStyle(document.body) ? "x9_4v2_b" : "bot"
        # Para Python, usamos sempre "x9_4v2_b" (ambiente web normal)
        identificador = "x9_4v2_b"
        
        # Calcula MD5(data + hostname::v2 + identificador)
        hash_input = data_atual + hostname_v2 + identificador
        md5_hash = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        
        # Primeiros 8 caracteres do MD5
        md5_suffix = md5_hash[:8]
        
        # Chave final: base + hash[:8]
        chave_final = base_key + md5_suffix
        
        return chave_final

    def _descriptografar_rabbit(self, encrypted_data:  str) -> dict:
        """
        Descriptografa dados usando algoritmo Rabbit (implementação Python pura)
        
        Args:
            encrypted_data: String criptografada em base64
            
        Returns:  
            Dicionário com dados descriptografados
        """
        try:
            # Gera a chave
            chave = self._gerar_chave_descriptografia()
            
            # Descriptografa usando implementação Python pura
            decrypted_json = _decrypt_rabbit_cipher(encrypted_data, chave)
            
            if 'error' in decrypted_json:
                raise Exception(f"Erro na descriptografia: {decrypted_json['error']}")
            
            return decrypted_json
            
        except Exception as e:  
            print(f"[Kuromangas] ❌ Erro ao descriptografar: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _processar_resposta_api(self, response) -> dict:
        """
        Processa resposta da API, descriptografando se necessário
        
        Args: 
            response:  Objeto response do requests
            
        Returns:  
            Dicionário com dados (descriptografados se necessário)
        """
        try:
            data = response.json()
            
            # Verifica se a resposta está criptografada
            if '_r_data' in data and '_auth' in data:
                # Descriptografa _r_data
                encrypted_data = data. get('_r_data', '')
                if encrypted_data: 
                    return self._descriptografar_rabbit(encrypted_data)
                else:
                    print("[Kuromangas] ⚠️ Campo '_r_data' vazio")
                    return {}
            else:
                # Resposta não está criptografada
                return data
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro ao processar resposta: {e}")
            return {}
    
    def _load_token(self):
        """Carrega o token de acesso salvo no banco de dados"""
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            self.access_token = login_info.headers.get('authorization').replace('Bearer ', '')
            self.headers['authorization'] = f'Bearer {self.access_token}'
            print("[Kuromangas] ✅ Token de acesso carregado")
    
    def _save_token(self, token: str):
        """Salva o token de acesso no banco de dados"""
        self.access_token = token
        self.headers['authorization'] = f'Bearer {token}'
        insert_login(LoginData(
            self.domain_name,
            {'authorization': f'Bearer {token}'},
            {}
        ))
        print("[Kuromangas] ✅ Token de acesso salvo")
    
    def login(self, force=False):
        """Realiza login na API do Kuromangas"""
        # Verifica se já tem token válido (se não for forçado)
        if not force:
            login_info = get_login(self.domain_name)
            if login_info and login_info.headers.get('authorization'):
                print("[Kuromangas] ✅ Login encontrado em cache")
                self._load_token()
                return True
        
        print("[Kuromangas] 🔐 Realizando login...")
        
        try:
            login_url = f'{self.api_base}/auth/login'
            
            # Credenciais de login
            payload = {
                "email": "opai@gmail.com",
                "password": "Opai@123"
            }
            
            response = Http.post(
                login_url,
                data=json.dumps(payload),
                headers=self.headers,
                timeout=15
            )
            
            if response.status in [200, 201]:
                # data = response.json()
                data = self._processar_resposta_api(response)
                token = data.get('token')
                user = data.get('user', {})
                
                if token:
                    self._save_token(token)
                    print(f"[Kuromangas] ✅ Login bem-sucedido! Usuário: {user.get('username', 'Desconhecido')}")
                    return True
                else:
                    print("[Kuromangas] ❌ Token não encontrado na resposta")
                    return False
            else:
                print(f"[Kuromangas] ❌ Falha no login - Status: {response.status}")
                return False
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro ao fazer login: {e}")
            return False
    
    def getManga(self, link: str) -> Manga:
        """Extrai informações do mangá via API"""
        # Garantir que temos token
        if not self.access_token:
            self.login()
        
        try:
            # Extrair ID do mangá da URL
            # Formato: https://beta.kuromangas.com/manga/1753
            match = re.search(r'/manga/(\d+)', link)
            if not match:
                raise Exception("ID do mangá não encontrado na URL")
                
            manga_id = match.group(1)
            
            api_url = f'{self.api_base}/mangas/{manga_id}'
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            # Se receber 401/403, força novo login
            if response.status_code in [401, 403]:
                print(f"[Kuromangas] ⚠️  Token inválido ({response.status_code}), forçando novo login...")
                if self.login(force=True):
                    # Retry com novo token
                    response = requests.get(api_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                # data = response.json()
                data = self._processar_resposta_api(response)
                manga_data = data.get('manga', {})
                title = manga_data.get('title', 'Título Desconhecido')
                print(f"[Kuromangas] Mangá encontrado: {title}")
                return Manga(link, title)
            else:
                raise Exception(f"API retornou status {response.status_code}")
            
        except Exception as e:
            print(f"[Kuromangas] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        """Extrai lista de capítulos via API"""
        # Garantir que temos token
        if not self.access_token:
            self.login()
        
        try:
            # Extrair ID do mangá
            match = re.search(r'/manga/(\d+)', manga_id)
            if not match:
                raise Exception("ID do mangá não encontrado")
                
            manga_num_id = match.group(1)
            
            api_url = f'{self.api_base}/mangas/{manga_num_id}'
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            # Se receber 401/403, força novo login
            if response.status_code in [401, 403]:
                print(f"[Kuromangas] ⚠️  Token inválido ({response.status_code}), forçando novo login...")
                if self.login(force=True):
                    response = requests.get(api_url, headers=self.headers, timeout=15)
            
            # data = response.json()
            data = self._processar_resposta_api(response)
            
            manga_data = data.get('manga', {})
            title = manga_data.get('title', 'Título Desconhecido')
            
            chapters_list = []
            for ch in data.get('chapters', []):
                chapter_id = ch['id']
                chapter_number = ch.get('chapter_number', 'Desconhecido')
                if '.00' in chapter_number:
                    chapter_number = chapter_number.replace('.00', '')
                elif chapter_number.endswith('0'):
                    chapter_number = chapter_number[:-1]
                
                chapters_list.append(Chapter(chapter_id, chapter_number, title))
            
            print(f"[Kuromangas] Encontrados {len(chapters_list)} capítulos")
            return chapters_list
            
        except Exception as e:
            print(f"[Kuromangas] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai páginas/imagens do capítulo via API"""
        # Garantir que temos token
        if not self.access_token:
            self.login()
        
        try:
            api_url = f"{self.api_base}/chapters/{ch.id}"
            print(f"[Kuromangas] Chamando API: {api_url}")
            
            response = requests.get(api_url, headers=self.headers, timeout=15)
            
            # Se receber 401/403, força novo login
            if response.status_code in [401, 403]:
                print(f"[Kuromangas] ⚠️  Token inválido ({response.status_code}), forçando novo login...")
                if self.login(force=True):
                    response = requests.get(api_url, headers=self.headers, timeout=15)
            
            # data = response.json()
            data = self._processar_resposta_api(response)
            
            pages = data.get('pages', [])
            
            # Construir URLs completas das imagens
            image_urls = []
            for page_path in pages:
                # As páginas vêm como /chapters/xxxxx.webp
                full_url = f"{self.cdn}{page_path}"
                image_urls.append(full_url)
            
            print(f"[Kuromangas] ✅ Encontradas {len(image_urls)} páginas")
            return Pages(ch.id, ch.number, ch.name, image_urls)
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro ao buscar páginas: {e}")
            return Pages(ch.id, ch.number, ch.name, [])
