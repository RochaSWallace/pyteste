import re
import json
import requests
import base64
import hashlib
from typing import List
from datetime import datetime
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from core.config.login_data import insert_login, LoginData, get_login


class RabbitCipher:
    """
    Implementação do Rabbit Stream Cipher - porta exata do CryptoJS.
    """
    
    def __init__(self):
        self._X = [0] * 8  # State variables
        self._C = [0] * 8  # Counter variables
        self._b = 0        # Counter carry bit
    
    @staticmethod
    def _u32(n):
        """Garante unsigned 32-bit"""
        return n & 0xFFFFFFFF
    
    @staticmethod
    def _swap_endian(word):
        """
        Byte swap - equivalente ao JavaScript:
        (word << 8 | word >>> 24) & 0x00ff00ff | (word << 24 | word >>> 8) & 0xff00ff00
        """
        word = word & 0xFFFFFFFF
        return (
            ((word << 8) | (word >> 24)) & 0x00FF00FF |
            ((word << 24) | (word >> 8)) & 0xFF00FF00
        ) & 0xFFFFFFFF
    
    def _next_state(self):
        """
        Função j() do CryptoJS - avança o estado interno.
        """
        X = self._X
        C = self._C
        
        # Salva contadores antigos
        C_old = C[:]
        
        # Atualiza contadores com constantes específicas
        C[0] = self._u32(C[0] + 0x4D34D34D + self._b)
        C[1] = self._u32(C[1] + 0xD34D34D3 + (1 if (C[0] & 0xFFFFFFFF) < (C_old[0] & 0xFFFFFFFF) else 0))
        C[2] = self._u32(C[2] + 0x34D34D34 + (1 if (C[1] & 0xFFFFFFFF) < (C_old[1] & 0xFFFFFFFF) else 0))
        C[3] = self._u32(C[3] + 0x4D34D34D + (1 if (C[2] & 0xFFFFFFFF) < (C_old[2] & 0xFFFFFFFF) else 0))
        C[4] = self._u32(C[4] + 0xD34D34D3 + (1 if (C[3] & 0xFFFFFFFF) < (C_old[3] & 0xFFFFFFFF) else 0))
        C[5] = self._u32(C[5] + 0x34D34D34 + (1 if (C[4] & 0xFFFFFFFF) < (C_old[4] & 0xFFFFFFFF) else 0))
        C[6] = self._u32(C[6] + 0x4D34D34D + (1 if (C[5] & 0xFFFFFFFF) < (C_old[5] & 0xFFFFFFFF) else 0))
        C[7] = self._u32(C[7] + 0xD34D34D3 + (1 if (C[6] & 0xFFFFFFFF) < (C_old[6] & 0xFFFFFFFF) else 0))
        self._b = 1 if (C[7] & 0xFFFFFFFF) < (C_old[7] & 0xFFFFFFFF) else 0
        
        # Calcula valores G (função g do Rabbit)
        G = []
        for i in range(8):
            # k = g[b] + N[b] (X + C)
            k = self._u32(X[i] + C[i])
            
            # Função g quadrática do CryptoJS
            v = k & 0xFFFF        # low 16 bits
            S = k >> 16           # high 16 bits
            
            # C = ((v * v >>> 17) + v * S >>> 15) + S * S
            C_val = self._u32(
                self._u32(
                    self._u32((v * v) >> 17) + self._u32(v * S)
                ) >> 15
            ) + self._u32(S * S)
            
            # E = ((k & 4294901760) * k | 0) + ((k & 65535) * k | 0)
            E_val = self._u32(
                self._u32((k & 0xFFFF0000) * k) + 
                self._u32((k & 0x0000FFFF) * k)
            )
            
            G.append(self._u32(C_val ^ E_val))
        
        # Atualiza estado X
        X[0] = self._u32(G[0] + ((G[7] << 16) | (G[7] >> 16)) + ((G[6] << 16) | (G[6] >> 16)))
        X[1] = self._u32(G[1] + ((G[0] << 8) | (G[0] >> 24)) + G[7])
        X[2] = self._u32(G[2] + ((G[1] << 16) | (G[1] >> 16)) + ((G[0] << 16) | (G[0] >> 16)))
        X[3] = self._u32(G[3] + ((G[2] << 8) | (G[2] >> 24)) + G[1])
        X[4] = self._u32(G[4] + ((G[3] << 16) | (G[3] >> 16)) + ((G[2] << 16) | (G[2] >> 16)))
        X[5] = self._u32(G[5] + ((G[4] << 8) | (G[4] >> 24)) + G[3])
        X[6] = self._u32(G[6] + ((G[5] << 16) | (G[5] >> 16)) + ((G[4] << 16) | (G[4] >> 16)))
        X[7] = self._u32(G[7] + ((G[6] << 8) | (G[6] >> 24)) + G[5])
    
    def _do_reset(self, key_words: list, iv_words: list = None):
        """
        _doReset do CryptoJS - inicializa o estado com a chave.
        """
        g = key_words[:]
        
        # IMPORTANTE: Byte swap na chave primeiro!
        for b in range(4):
            g[b] = self._swap_endian(g[b])
        
        # Inicializa X (state variables)
        self._X[0] = g[0]
        self._X[1] = self._u32((g[3] << 16) | (g[2] >> 16))
        self._X[2] = g[1]
        self._X[3] = self._u32((g[0] << 16) | (g[3] >> 16))
        self._X[4] = g[2]
        self._X[5] = self._u32((g[1] << 16) | (g[0] >> 16))
        self._X[6] = g[3]
        self._X[7] = self._u32((g[2] << 16) | (g[1] >> 16))
        
        # Inicializa C (counter variables)
        self._C[0] = self._u32((g[2] << 16) | (g[2] >> 16))
        self._C[1] = (g[0] & 0xFFFF0000) | (g[1] & 0x0000FFFF)
        self._C[2] = self._u32((g[3] << 16) | (g[3] >> 16))
        self._C[3] = (g[1] & 0xFFFF0000) | (g[2] & 0x0000FFFF)
        self._C[4] = self._u32((g[0] << 16) | (g[0] >> 16))
        self._C[5] = (g[2] & 0xFFFF0000) | (g[3] & 0x0000FFFF)
        self._C[6] = self._u32((g[1] << 16) | (g[1] >> 16))
        self._C[7] = (g[3] & 0xFFFF0000) | (g[0] & 0x0000FFFF)
        
        self._b = 0
        
        # Itera 4 vezes
        for _ in range(4):
            self._next_state()
        
        # XOR counters com state
        for i in range(8):
            self._C[i] ^= self._X[(i + 4) & 7]
        
        # Setup IV se presente
        if iv_words:
            S = iv_words
            C_iv = S[0]
            E = S[1]
            
            # Byte swap no IV
            P = self._swap_endian(C_iv)
            L = self._swap_endian(E)
            
            B = (P >> 16) | (L & 0xFFFF0000)
            D = self._u32((L << 16) | (P & 0x0000FFFF))
            
            self._C[0] ^= P
            self._C[1] ^= B
            self._C[2] ^= L
            self._C[3] ^= D
            self._C[4] ^= P
            self._C[5] ^= B
            self._C[6] ^= L
            self._C[7] ^= D
            
            for _ in range(4):
                self._next_state()
    
    def _generate_keystream_block(self) -> list:
        """
        _doProcessBlock do CryptoJS - gera um bloco de keystream.
        Retorna 4 palavras de 32 bits.
        """
        self._next_state()
        
        X = self._X
        
        # Extrai keystream
        x = [0] * 4
        x[0] = self._u32(X[0] ^ (X[5] >> 16) ^ (X[3] << 16))
        x[1] = self._u32(X[2] ^ (X[7] >> 16) ^ (X[5] << 16))
        x[2] = self._u32(X[4] ^ (X[1] >> 16) ^ (X[7] << 16))
        x[3] = self._u32(X[6] ^ (X[3] >> 16) ^ (X[1] << 16))
        
        # IMPORTANTE: Byte swap no output!
        for k in range(4):
            x[k] = self._swap_endian(x[k])
        
        return x
    
    def decrypt(self, ciphertext: bytes, key: bytes, iv: bytes = None) -> bytes:
        """Descriptografa dados usando Rabbit"""
        # Converte key para words (big-endian)
        key = (key + b'\x00' * 16)[:16]
        key_words = []
        for i in range(4):
            key_words.append(
                (key[i*4] << 24) | (key[i*4+1] << 16) | 
                (key[i*4+2] << 8) | key[i*4+3]
            )
        
        # Converte IV para words se presente
        iv_words = None
        if iv:
            iv = (iv + b'\x00' * 8)[:8]
            iv_words = []
            for i in range(2):
                iv_words.append(
                    (iv[i*4] << 24) | (iv[i*4+1] << 16) | 
                    (iv[i*4+2] << 8) | iv[i*4+3]
                )
        
        # Reset e inicializa
        self._X = [0] * 8
        self._C = [0] * 8
        self._b = 0
        self._do_reset(key_words, iv_words)
        
        # Processa dados
        result = bytearray()
        pos = 0
        
        while pos < len(ciphertext):
            # Gera bloco de keystream
            keystream_words = self._generate_keystream_block()
            
            # Converte para bytes (big-endian)
            keystream = bytearray()
            for word in keystream_words:
                keystream.append((word >> 24) & 0xFF)
                keystream.append((word >> 16) & 0xFF)
                keystream.append((word >> 8) & 0xFF)
                keystream.append(word & 0xFF)
            
            # XOR com ciphertext
            chunk_size = min(16, len(ciphertext) - pos)
            for i in range(chunk_size):
                result.append(ciphertext[pos + i] ^ keystream[i])
            
            pos += chunk_size
        
        return bytes(result)


def evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 16, iv_len: int = 8) -> tuple:
    """EVP_BytesToKey do OpenSSL"""
    derived = b''
    block = b''
    while len(derived) < key_len + iv_len:
        block = hashlib.md5(block + password + salt).digest()
        derived += block
    return derived[:key_len], derived[key_len:key_len + iv_len]


def cryptojs_rabbit_decrypt(encrypted_base64: str, passphrase: str) -> str:
    """Descriptografa dados do CryptoJS.Rabbit"""
    # Decode base64
    try:
        encrypted_data = base64.b64decode(encrypted_base64)
    except Exception:
        padding = 4 - len(encrypted_base64) % 4
        if padding != 4:
            encrypted_base64 += '=' * padding
        encrypted_data = base64.b64decode(encrypted_base64)
    
    # Formato OpenSSL: "Salted__" + salt(8) + ciphertext
    if encrypted_data[:8] == b'Salted__':
        salt = encrypted_data[8:16]
        ciphertext = encrypted_data[16:]
        key, iv = evp_bytes_to_key(passphrase.encode('utf-8'), salt)
    else:
        ciphertext = encrypted_data
        key = hashlib.md5(passphrase.encode('utf-8')).digest()
        iv = None
    
    # Descriptografa
    cipher = RabbitCipher()
    plaintext = cipher.decrypt(ciphertext, key, iv)
    
    # Remove PKCS7 padding
    if plaintext:
        pad_len = plaintext[-1]
        if 0 < pad_len <= 16 and all(b == pad_len for b in plaintext[-pad_len:]):
            plaintext = plaintext[:-pad_len]
    
    return plaintext.decode('utf-8', errors='ignore')


# ============================================================================
# PROVIDER KUROMANGAS
# ============================================================================

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
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type": "application/json",
            "origin": self.base,
            "referer": f"{self.base}/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._load_token()

    def _gerar_chave_descriptografia(self) -> str:
        """
        Gera a chave de descriptografia dinâmica do KuroMangas.
        CORRIGIDO: base_key correta extraída do JavaScript
        """
        # CHAVE CORRETA do JavaScript!
        base_key = "53to8l674shjk6sjsksdfE2oMwkajkun9TuYTudsWIF4jeKdqEwhUEft97879147pasd235as"
        
        # Data atual no formato ISO (YYYY-MM-DD)
        data_atual = datetime.now().strftime("%Y-%m-%d")
        
        # Hostname com ::v2
        hostname_v2 = "beta.kuromangas.com::v2"
        
        # Identificador (no Python sempre usamos "x9_4v2_b")
        identificador = "x9_4v2_b"
        
        # MD5(data + hostname + identificador)[:8]
        hash_input = data_atual + hostname_v2 + identificador
        md5_hash = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        md5_suffix = md5_hash[:8]
        
        chave_final = base_key + md5_suffix
        return chave_final

    def _descriptografar_rabbit(self, encrypted_data: str) -> dict:
        """Descriptografa dados usando Rabbit cipher"""
        try:
            chave = self._gerar_chave_descriptografia()
            print(f"[Kuromangas] 🔑 Chave: {chave[:40]}...{chave[-12:]}")
            
            decrypted_str = cryptojs_rabbit_decrypt(encrypted_data, chave)
            
            if not decrypted_str or not decrypted_str.strip():
                print("[Kuromangas] ⚠️ Resultado vazio")
                return {}
            
            # Encontra JSON válido
            start = decrypted_str.find('{')
            end = decrypted_str.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = decrypted_str[start:end]
                decrypted_json = json.loads(json_str)
            else:
                decrypted_json = json.loads(decrypted_str)
            
            if '_wrapped' in decrypted_json:
                return decrypted_json['_wrapped']
            
            return decrypted_json
            
        except json.JSONDecodeError as e:
            print(f"[Kuromangas] ❌ Erro JSON: {e}")
            if decrypted_str:
                print(f"[Kuromangas] 📝 Output: {repr(decrypted_str[:300])}")
            return {}
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _processar_resposta_api(self, response) -> dict:
        """Processa resposta da API"""
        try:
            data = response.json()
            
            if '_v_secure' in data:
                encrypted_data = data.get('_v_secure', '')
                if encrypted_data:
                    print("[Kuromangas] 🔐 Formato _v_secure detectado")
                    return self._descriptografar_rabbit(encrypted_data)
                return {}
            
            elif '_r_data' in data and '_auth' in data:
                encrypted_data = data.get('_r_data', '')
                if encrypted_data:
                    print("[Kuromangas] 🔐 Formato _r_data detectado")
                    return self._descriptografar_rabbit(encrypted_data)
                return {}
            
            return data
                
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro: {e}")
            return {}

    def _load_token(self):
        login_info = get_login(self.domain_name)
        if login_info and login_info.headers.get('authorization'):
            self.access_token = login_info.headers.get('authorization').replace('Bearer ', '')
            self.headers['authorization'] = f'Bearer {self.access_token}'
            print("[Kuromangas] ✅ Token carregado")

    def _save_token(self, token: str):
        self.access_token = token
        self.headers['authorization'] = f'Bearer {token}'
        insert_login(LoginData(self.domain_name, {'authorization': f'Bearer {token}'}, {}))
        print("[Kuromangas] ✅ Token salvo")

    def login(self, force=False):
        if not force:
            login_info = get_login(self.domain_name)
            if login_info and login_info.headers.get('authorization'):
                print("[Kuromangas] ✅ Login em cache")
                self._load_token()
                return True
        
        print("[Kuromangas] 🔐 Fazendo login...")
        
        try:
            response = requests.post(
                f'{self.api_base}/auth/login',
                data=json.dumps({"email": "opai@gmail.com", "password": "Opai@123"}),
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                data = self._processar_resposta_api(response)
                token = data.get('token')
                if token:
                    self._save_token(token)
                    print(f"[Kuromangas] ✅ Login OK!")
                    return True
            return False
        except Exception as e:
            print(f"[Kuromangas] ❌ Erro: {e}")
            return False

    def getManga(self, link: str) -> Manga:
        if not self.access_token:
            self.login()
        
        match = re.search(r'/manga/(\d+)', link)
        if not match:
            raise Exception("ID não encontrado")
        
        response = requests.get(
            f'{self.api_base}/mangas/{match.group(1)}',
            headers=self.headers, timeout=15
        )
        
        if response.status_code in [401, 403]:
            if self.login(force=True):
                response = requests.get(
                    f'{self.api_base}/mangas/{match.group(1)}',
                    headers=self.headers, timeout=15
                )
        
        data = self._processar_resposta_api(response)
        title = data.get('manga', {}).get('title', 'Desconhecido')
        print(f"[Kuromangas] ✅ Mangá: {title}")
        return Manga(link, title)

    def getChapters(self, manga_id: str) -> List[Chapter]:
        if not self.access_token:
            self.login()
        
        match = re.search(r'/manga/(\d+)', manga_id)
        if not match:
            return []
        
        response = requests.get(
            f'{self.api_base}/mangas/{match.group(1)}',
            headers=self.headers, timeout=15
        )
        
        if response.status_code in [401, 403]:
            if self.login(force=True):
                response = requests.get(
                    f'{self.api_base}/mangas/{match.group(1)}',
                    headers=self.headers, timeout=15
                )
        
        data = self._processar_resposta_api(response)
        title = data.get('manga', {}).get('title', 'Desconhecido')
        
        chapters = []
        for ch in data.get('chapters', []):
            num = str(ch.get('chapter_number', '?')).replace('.00', '')
            chapters.append(Chapter(ch['id'], num, title))
        
        print(f"[Kuromangas] ✅ {len(chapters)} capítulos")
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        if not self.access_token:
            self.login()
        
        response = requests.get(
            f"{self.api_base}/chapters/{ch.id}",
            headers=self.headers, timeout=15
        )
        
        if response.status_code in [401, 403]:
            if self.login(force=True):
                response = requests.get(
                    f"{self.api_base}/chapters/{ch.id}",
                    headers=self.headers, timeout=15
                )
        
        data = self._processar_resposta_api(response)
        urls = [f"{self.cdn}{p}" for p in data.get('pages', [])]
        
        print(f"[Kuromangas] ✅ {len(urls)} páginas")
        return Pages(ch.id, ch.number, ch.name, urls)