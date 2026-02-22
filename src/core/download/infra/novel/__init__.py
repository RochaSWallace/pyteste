import os
import re
import base64
import random
import requests
import cloudscraper
import tldextract
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional, List, Dict
from core.config.img_conf import get_config
from core.__seedwork.infra.http import Http
from core.providers.domain.page_entity import Pages
from core.download.domain.dowload_entity import Chapter
from core.download.domain.dowload_repository import DownloadRepository
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from core.cloudflare.infra.seleniumbase_bypass import (
    bypass_cloudflare_with_seleniumbase,
    bypass_cloudflare_get_html_with_seleniumbase
)
from core.config.request_data import get_request, delete_request, insert_request, RequestData


# ==================== SINGLETON GLOBAL PARA PROXY ROTATOR ====================
# Evita deadlock quando múltiplas threads tentam criar ProxyRotator simultaneamente
_global_proxy_rotator = None
_proxy_rotator_lock = None

def get_proxy_rotator():
    """Retorna instância singleton de ProxyRotator (thread-safe)"""
    global _global_proxy_rotator, _proxy_rotator_lock
    
    # Inicializar lock se necessário (importação lazy para evitar circular imports)
    if _proxy_rotator_lock is None:
        import threading
        _proxy_rotator_lock = threading.Lock()
    
    # Double-checked locking pattern
    if _global_proxy_rotator is None:
        with _proxy_rotator_lock:
            if _global_proxy_rotator is None:
                _global_proxy_rotator = ProxyRotator()
    
    return _global_proxy_rotator


class ProxyRotator:
    """Gerenciador de proxies gratuitos com rotação automática (SINGLETON)"""
    
    def __init__(self):
        import threading
        self.proxies: List[Dict[str, str]] = []
        self.current_index = 0
        self.failed_proxies = set()
        self._lock = threading.Lock()  # Lock para operações thread-safe
        self._load_free_proxies()
    
    def _load_free_proxies(self):
        """Carrega lista de proxies gratuitos públicos"""
        # Lista de proxies HTTP gratuitos (atualize periodicamente)
        # Fonte: https://www.proxy-list.download/HTTP
        free_proxy_list = [
            {'http': 'http://47.88.3.19:8080', 'https': 'http://47.88.3.19:8080'},
            {'http': 'http://103.152.112.145:80', 'https': 'http://103.152.112.145:80'},
            {'http': 'http://20.204.212.76:3129', 'https': 'http://20.204.212.76:3129'},
            {'http': 'http://188.132.222.41:8080', 'https': 'http://188.132.222.41:8080'},
            {'http': 'http://103.48.68.36:84', 'https': 'http://103.48.68.36:84'},
        ]
        
        # Embaralhar para distribuir uso
        random.shuffle(free_proxy_list)
        self.proxies = free_proxy_list
        print(f"🔄 Proxies carregados: {len(self.proxies)} disponíveis")
    
    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        """Retorna próximo proxy disponível (rotação circular) - THREAD-SAFE"""
        with self._lock:
            if not self.proxies:
                return None
            
            # Tentar até 3 proxies diferentes
            attempts = 0
            max_attempts = min(3, len(self.proxies))
            
            while attempts < max_attempts:
                proxy = self.proxies[self.current_index]
                proxy_url = proxy.get('http', '')
                
                # Pular proxies que falharam recentemente
                if proxy_url not in self.failed_proxies:
                    self.current_index = (self.current_index + 1) % len(self.proxies)
                    return proxy
                
                self.current_index = (self.current_index + 1) % len(self.proxies)
                attempts += 1
            
            # Se todos falharam, limpar lista de falhas e tentar novamente
            self.failed_proxies.clear()
            return self.proxies[self.current_index] if self.proxies else None
    
    def mark_proxy_failed(self, proxy: Dict[str, str]):
        """Marca proxy como falho para evitar reutilização imediata - THREAD-SAFE"""
        with self._lock:
            proxy_url = proxy.get('http', '')
            if proxy_url:
                self.failed_proxies.add(proxy_url)


class NovelDownloadRepository(DownloadRepository):
    """Repositório de download para novels - converte HTML para Markdown"""

    def __init__(self, cdn_base_url: str = "https://cdn.mediocrescan.com"):
        """
        Inicializa o repositório de download de novels
        
        Args:
            cdn_base_url: URL base do CDN para construir URLs das imagens
        """
        self.cdn_base_url = cdn_base_url.rstrip('/')
        self.s3_uploader = self._create_s3_uploader()
        # Usar singleton compartilhado para evitar deadlock em downloads paralelos
        self.proxy_rotator = get_proxy_rotator()
        self.use_proxy = True  # Flag para habilitar/desabilitar proxies
    
    def _create_s3_uploader(self):
        """
        Cria instância de S3BucketUtils para upload de imagens
        
        Returns:
            S3BucketUtils configurado ou None se não disponível
        """
        try:
            from mediocre_upload.upload_images import S3BucketUtils
            
            # Credenciais do R2
            R2_ACCOUNT_ID = "7aac7fea564713dbc3c89ca83ea5b827"
            R2_ACCESS_KEY_ID = "6b4645bc19e2741157ebf4bf74b1aa10"
            R2_SECRET_ACCESS_KEY = "c9f782393666568e1755e1edaaced58b0001bb998dc53737147a063134f97c04"
            R2_BUCKET = "mediocre-images"
            
            return S3BucketUtils(
                account_id=R2_ACCOUNT_ID,
                access_key=R2_ACCESS_KEY_ID,
                secret_key=R2_SECRET_ACCESS_KEY,
                bucket=R2_BUCKET
            )
        except ImportError:
            print("⚠️  S3BucketUtils não disponível. Imagens serão embutidas em base64.")
            return None
    
    def _fetch_with_proxy(self, url: str, headers=None, cookies=None, timeout=30) -> Optional[str]:
        """
        Faz requisição HTTP usando proxy rotativo com fallback para SeleniumBase
        COM CACHE DE COOKIES para evitar abrir navegador toda vez
        
        Args:
            url: URL para acessar
            headers: Headers HTTP
            cookies: Cookies HTTP
            timeout: Timeout da requisição
        
        Returns:
            str: HTML da página ou None se falhar
        """
        # Extrair domínio para cache de cookies
        extract = tldextract.extract(url)
        domain = f"{extract.domain}.{extract.suffix}"
        
        # Criar scraper base
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # 1️⃣ Tentar com COOKIES SALVOS primeiro (mais rápido!)
        request_data = get_request(domain)
        if request_data:
            try:
                merged_headers = {**headers} if headers else {}
                merged_headers.update(request_data.headers)
                
                merged_cookies = {**cookies} if cookies else {}
                merged_cookies.update(request_data.cookies)
                
                print(f"🍪 Tentando com cookies salvos para {domain}")
                response = scraper.get(
                    url,
                    headers=merged_headers,
                    cookies=merged_cookies,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    print(f"✅ Sucesso com cookies salvos!")
                    return response.text
                elif response.status_code == 403:
                    print(f"🔒 Cookies expirados, limpando cache...")
                    delete_request(domain)
            except Exception as e:
                print(f"⚠️ Falha com cookies salvos: {str(e)[:100]}")
                delete_request(domain)
        
        # 2️⃣ Tentar com PROXY (se habilitado)
        if self.use_proxy:
            proxy = self.proxy_rotator.get_next_proxy()
            
            if proxy:
                try:
                    print(f"🔄 Tentando com proxy: {proxy.get('http', 'unknown')}")
                    response = scraper.get(
                        url,
                        headers=headers,
                        cookies=cookies,
                        proxies=proxy,
                        timeout=timeout
                    )
                    
                    if response.status_code == 200:
                        print(f"✅ Sucesso com proxy!")
                        return response.text
                    elif response.status_code == 403:
                        print(f"🔒 Bloqueio Cloudflare com proxy")
                        self.proxy_rotator.mark_proxy_failed(proxy)
                    else:
                        print(f"⚠️ Proxy retornou status {response.status_code}")
                        self.proxy_rotator.mark_proxy_failed(proxy)
                
                except Exception as e:
                    print(f"❌ Falha no proxy: {str(e)[:100]}")
                    self.proxy_rotator.mark_proxy_failed(proxy)
        
        # 3️⃣ Fallback: Obter COOKIES com SeleniumBase e salvar para reutilização
        print(f"🤖 Obtendo cookies com SeleniumBase para {domain}")
        try:
            # Usar bypass que retorna COOKIES (não apenas HTML)
            data = bypass_cloudflare_with_seleniumbase(
                url=f'https://{domain}',
                xvfb=True,
                headless=False,
                reconnect_time=3.0
            )
            
            if data and data.cloudflare_cookie_value:
                # Salvar cookies para reutilização futura
                insert_request(RequestData(
                    domain=domain,
                    headers=data.user_agent,
                    cookies=data.cloudflare_cookie_value
                ))
                print(f"✅ Cookies salvos para {domain}! Próximas requisições serão rápidas.")
                
                # Fazer requisição com os cookies obtidos
                response = scraper.get(
                    url,
                    headers=data.user_agent,
                    cookies=data.cloudflare_cookie_value,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    return response.text
        
        except Exception as e:
            print(f"⚠️ Falha ao obter cookies: {str(e)[:100]}")
        
        # 4️⃣ Último recurso: Obter HTML diretamente
        print(f"🌐 Obtendo HTML diretamente com SeleniumBase...")
        try:
            content = bypass_cloudflare_get_html_with_seleniumbase(
                url=url,
                xvfb=True,
                headless=False,
                reconnect_time=3.0
            )
            
            if content:
                print(f"✅ SeleniumBase HTML obtido!")
                return content
        
        except Exception as e:
            print(f"❌ Falha no SeleniumBase: {str(e)}")
        
        return None

    def download(self, pages: Pages, fn=None, headers=None, cookies=None, timeout=None) -> Chapter:
        """
        Baixa capítulos de novel e salva como arquivos Markdown
        
        Args:
            pages: Objeto Pages contendo URL do capítulo
            fn: Função de callback para progresso
            headers: Headers HTTP
            cookies: Cookies HTTP
            timeout: Timeout da requisição
        
        Returns:
            Chapter: Objeto contendo número e lista de arquivos salvos
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title))
        os.makedirs(path, exist_ok=True)

        files = []
        failed_count = 0  # Contador de falhas
        total_pages = len(pages.pages)
        max_failures_allowed = 0  # Limite de falhas antes de abortar
        
        # Para novels, pages.pages contém a URL do capítulo
        for i, chapter_url in enumerate(pages.pages):
            try:
                # Faz a requisição HTTP com proxy e fallback para SeleniumBase
                html_content = self._fetch_with_proxy(
                    chapter_url,
                    headers=headers,
                    cookies=cookies,
                    timeout=timeout or 30
                )
                
                if not html_content:
                    raise Exception(f"Falha ao obter HTML para {chapter_url}")
                
                # Converte HTML para Markdown (com imagens em base64)
                markdown_content = self._html_to_markdown(
                    html_content.encode('utf-8'), 
                    chapter_url,
                    headers,
                    cookies,
                    timeout
                )
                
                # Gera nome do arquivo
                file_name = f"{sanitize_folder_name(pages.number)}.md"
                file_path = os.path.join(path, file_name)
                
                # Salva o arquivo Markdown
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                
                files.append(file_path)
                print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:green;'>Saved</span> {file_name}")
                
            except Exception as e:
                print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:red;'>Error</span> {e}")
                failed_count += 1
                
                # CRÍTICO: Abortar download se exceder limite de falhas
                if failed_count > max_failures_allowed:
                    raise Exception(f"Download abortado: {failed_count} falhas detectadas (limite: {max_failures_allowed}). Tentando novamente...")

            if fn is not None:
                progress = ((i + 1) * 100) / len(pages.pages)
                fn(progress)
        
        # CRÍTICO: Se algum capítulo falhou, levantar exceção para acionar sistema de retry
        if failed_count > 0:
            raise Exception(f"Falha ao baixar {failed_count} de {total_pages} capítulos")

        return Chapter(pages.number, files)

    def _html_to_markdown(self, html_content: bytes, url: str, headers=None, cookies=None, timeout=None) -> str:
        """
        Converte HTML de capítulo para formato Markdown com imagens embutidas em base64
        
        Args:
            html_content: HTML do capítulo em bytes
            url: URL do capítulo (para resolver URLs relativas)
            headers: Headers HTTP para download de imagens
            cookies: Cookies HTTP para download de imagens
            timeout: Timeout para download de imagens
        
        Returns:
            str: Conteúdo em formato Markdown com imagens em base64
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        markdown_lines = []
        
        # Extrai título do capítulo
        title_elem = soup.select_one('h1.entry-title')
        if title_elem:
            title = title_elem.get_text(separator=' ', strip=True)
            # Remove quebras de linha e espaços múltiplos
            title = re.sub(r'\s+', ' ', title).strip()
            markdown_lines.append(f"# {title}\n")
        
        # Extrai subtítulo (se houver)
        subtitle_elem = soup.select_one('div.cat-series')
        if subtitle_elem:
            subtitle = subtitle_elem.get_text(separator=' ', strip=True)
            # Remove quebras de linha e espaços múltiplos
            subtitle = re.sub(r'\s+', ' ', subtitle).strip()
            markdown_lines.append(f"## {subtitle}\n")
        
        # Contador de imagens para este capítulo
        img_counter = 1
        
        # Extrai conteúdo principal
        content_elem = soup.select_one('div.epcontent.entry-content')
        if content_elem:
            # Remove elementos indesejados
            for unwanted in content_elem.select('script, style, .socialts, .navimedia, .entry-info'):
                unwanted.decompose()
            
            # Processa cada parágrafo
            for p in content_elem.find_all('p'):
                # Primeiro verifica se há imagens no parágrafo
                images = p.find_all('img')
                if images:
                    for img in images:
                        img_url = img.get('src') or img.get('data-src')
                        if img_url:
                            # Resolve URL absoluta
                            absolute_url = urljoin(url, img_url)
                            
                            # Converte imagem para base64
                            base64_data = self._image_to_base64(
                                absolute_url,
                                headers,
                                cookies,
                                timeout
                            )
                            
                            if base64_data:
                                img_title = img.get('title') or img.get('alt') or f'Imagem {img_counter}'
                                markdown_lines.append(f"\n![{img_title}]({base64_data})\n")
                                img_counter += 1
                    continue
                
                text = p.get_text(strip=True)
                if text:
                    # Remove espaços extras
                    text = re.sub(r'\s+', ' ', text)
                    
                    # Filtra informações do site (tradução automática, revisores, etc)
                    if self._is_site_metadata(text):
                        continue
                    
                    # Verifica se é texto centralizado (geralmente notas)
                    if 'text-align: center' in p.get('style', '') or 'text-align:center' in p.get('style', ''):
                        markdown_lines.append(f"\n*{text}*\n")
                    else:
                        markdown_lines.append(f"\n{text}\n")
            
            # Processa outros elementos de texto
            for elem in content_elem.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = elem.get_text(strip=True)
                if text:
                    level = int(elem.name[1])
                    markdown_lines.append(f"\n{'#' * level} {text}\n")
        
        return '\n'.join(markdown_lines)
    
    def _image_to_base64(self, url: str, headers=None, cookies=None, timeout=None) -> str:
        """
        Baixa uma imagem e converte para base64 Data URI OU faz upload para CDN
        
        Args:
            url: URL da imagem
            headers: Headers HTTP
            cookies: Cookies HTTP
            timeout: Timeout da requisição
        
        Returns:
            str: Se s3_uploader estiver configurado, retorna URL do CDN.
                 Caso contrário, retorna Data URI em base64 (data:image/jpeg;base64,...).
                 Retorna None se falhar.
        """
        try:
            # Baixa a imagem
            response = Http.get(url, headers=headers, cookies=cookies, timeout=timeout)
            
            # Detecta o tipo MIME da imagem pela extensão da URL
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            
            # Mapeamento de extensões para MIME types
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp',
                '.svg': 'image/svg+xml'
            }
            
            # Tenta detectar pela extensão
            mime_type = 'image/jpeg'  # padrão
            extensao = 'jpg'  # padrão
            for ext, mime in mime_types.items():
                if path.endswith(ext):
                    mime_type = mime
                    extensao = ext.lstrip('.')
                    break
            
            # Se tem uploader configurado, faz upload para o CDN
            if self.s3_uploader:
                nome_arquivo = self.s3_uploader.upload_imagem_novel(response.content, extensao)
                if nome_arquivo:
                    cdn_url = f"{self.cdn_base_url}/novels/{nome_arquivo}"
                    print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:blue;'>Image uploaded</span> {cdn_url}")
                    return cdn_url
                else:
                    print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:red;'>Upload failed</span> {url}")
                    return None
            
            # Caso contrário, converte para base64 (método antigo)
            base64_data = base64.b64encode(response.content).decode('utf-8')
            
            # Retorna Data URI
            data_uri = f"data:{mime_type};base64,{base64_data}"
            
            print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:blue;'>Image embedded</span> {url}")
            return data_uri
            
        except Exception as e:
            print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:red;'>Image error</span> {url}: {e}")
            return None
    
    def _is_site_metadata(self, text: str) -> bool:
        """
        Verifica se o texto é metadata do site que deve ser filtrada
        
        Args:
            text: Texto a ser verificado
        
        Returns:
            bool: True se for metadata do site, False caso contrário
        """
        # Lista de padrões para filtrar
        filter_patterns = [
            r'tradução automática',
            r'revisado por',
            r'traduzido por',
            r'autor:',
            r'fonte:',
            r'postado por',
            r'visualizações',
            r'lançado em',
        ]
        
        text_lower = text.lower()
        
        # Verifica cada padrão
        for pattern in filter_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
