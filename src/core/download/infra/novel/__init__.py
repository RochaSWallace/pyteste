import os
import re
import base64
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from core.config.img_conf import get_config
from core.__seedwork.infra.http import Http
from core.providers.domain.page_entity import Pages
from core.download.domain.dowload_entity import Chapter
from core.download.domain.dowload_repository import DownloadRepository
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name


class NovelDownloadRepository(DownloadRepository):
    """Repositório de download para novels - converte HTML para Markdown"""

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
        
        # Para novels, pages.pages contém a URL do capítulo
        for i, chapter_url in enumerate(pages.pages):
            try:
                # Faz a requisição HTTP
                response = Http.get(chapter_url, headers=headers, cookies=cookies, timeout=timeout)
                
                # Converte HTML para Markdown (com imagens em base64)
                markdown_content = self._html_to_markdown(
                    response.content, 
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

            if fn is not None:
                progress = ((i + 1) * 100) / len(pages.pages)
                fn(progress)

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
        Baixa uma imagem e converte para base64 Data URI
        
        Args:
            url: URL da imagem
            headers: Headers HTTP
            cookies: Cookies HTTP
            timeout: Timeout da requisição
        
        Returns:
            str: Data URI em base64 (data:image/jpeg;base64,...), ou None se falhar
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
            for ext, mime in mime_types.items():
                if path.endswith(ext):
                    mime_type = mime
                    break
            
            # Converte para base64
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
