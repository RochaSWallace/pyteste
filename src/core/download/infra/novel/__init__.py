import os
import re
import base64
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib.parse import urljoin, urlparse
from typing import Optional
from core.config.img_conf import get_config
from core.__seedwork.infra.http import Http
from core.providers.domain.page_entity import Pages
from core.download.domain.dowload_entity import Chapter
from core.download.domain.dowload_repository import DownloadRepository
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name


class NovelDownloadRepository(DownloadRepository):
    """
    Repositório de download para novels - converte HTML padronizado para Markdown
    
    FORMATO PADRÃO DE ENTRADA (pages.pages[0]):
    {
        'html': '<article>...</article>',  # HTML estruturado do capítulo
        'title': 'Título do Capítulo',     # Título (opcional, pode estar no HTML)
        'url': 'https://...'               # URL base para resolver imagens relativas
    }
    
    TAGS HTML SUPORTADAS:
    - <h1>, <h2>, <h3>: Títulos (convertidos para # ## ###)
    - <p>: Parágrafos normais
    - <p class="italic"> ou <em>: Texto em itálico (*texto*)
    - <blockquote>: Citações/cartas (convertido para bloco ```)
    - <div class="system-box">: Caixas de sistema (convertido para bloco ```)
    - <img src="url" alt="desc">: Imagens (baixadas e upload para CDN)
    - <hr>: Separadores (convertido para ---)
    - <strong>, <b>: Negrito (**texto**)
    """

    def __init__(self, cdn_base_url: str = "https://cdn.mediocrescan.com"):
        """
        Inicializa o repositório de download de novels
        
        Args:
            cdn_base_url: URL base do CDN para construir URLs das imagens
        """
        self.cdn_base_url = cdn_base_url.rstrip('/')

    def download(self, pages: Pages, fn=None, headers=None, cookies=None, timeout=None) -> Chapter:
        """
        Baixa capítulos de novel e salva como arquivos Markdown
        
        Args:
            pages: Objeto Pages contendo dados estruturados do capítulo
                   pages.pages[0] deve conter dict com 'html', 'title', 'url'
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
        failed_count = 0
        total_pages = len(pages.pages)
        max_failures_allowed = 0
        
        for i, page_data in enumerate(pages.pages):
            try:
                # Formato padrão: dict com 'html', 'title', 'url'
                if isinstance(page_data, dict) and 'html' in page_data:
                    markdown_content = self._convert_html_to_markdown(
                        page_data,
                        headers,
                        cookies,
                        timeout
                    )
                else:
                    raise ValueError(
                        "Formato inválido: pages.pages deve conter dict com chave 'html'. "
                        "Use o formato padrão: {'html': '<article>...</article>', 'title': '...', 'url': '...'}"
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
                
                if failed_count > max_failures_allowed:
                    raise Exception(f"Download abortado: {failed_count} falhas detectadas (limite: {max_failures_allowed}). Tentando novamente...")

            if fn is not None:
                progress = ((i + 1) * 100) / len(pages.pages)
                fn(progress)
        
        if failed_count > 0:
            raise Exception(f"Falha ao baixar {failed_count} de {total_pages} capítulos")

        return Chapter(pages.number, files)

    def _convert_html_to_markdown(self, data: dict, headers=None, cookies=None, timeout=None) -> str:
        """
        Converte HTML padronizado para Markdown, processando imagens
        
        Args:
            data: Dict com 'html', 'title' (opcional), 'url' (para resolver URLs relativas)
            headers: Headers HTTP para download de imagens
            cookies: Cookies HTTP
            timeout: Timeout
        
        Returns:
            str: Conteúdo em formato Markdown
        """
        html_content = data.get('html', '')
        base_url = data.get('url', '')
        title_override = data.get('title', '')
        
        soup = BeautifulSoup(html_content, 'html.parser')
        markdown_lines = []
        
        # Título do data ou do HTML
        if title_override:
            markdown_lines.append(f"# {title_override}\n")
        
        # Processa elementos na ordem que aparecem
        for element in soup.children:
            self._process_element(element, markdown_lines, base_url, headers, cookies, timeout)
        
        # Limpa e junta
        result = '\n'.join(markdown_lines)
        # Remove múltiplas linhas em branco consecutivas
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()
    
    def _process_element(self, element, markdown_lines: list, base_url: str, 
                         headers=None, cookies=None, timeout=None, depth=0):
        """
        Processa recursivamente um elemento HTML e adiciona Markdown correspondente
        
        Args:
            element: Elemento BeautifulSoup
            markdown_lines: Lista para acumular linhas Markdown
            base_url: URL base para resolver URLs relativas
            headers, cookies, timeout: Parâmetros HTTP
            depth: Profundidade da recursão (para evitar loops)
        """
        if depth > 50:  # Limite de profundidade para segurança
            return
            
        if isinstance(element, NavigableString):
            # Texto puro fora de tags - ignorar se só whitespace
            text = str(element).strip()
            if text:
                markdown_lines.append(f"\n{text}\n")
            return
        
        if not isinstance(element, Tag):
            return
        
        tag_name = element.name.lower() if element.name else ''
        
        # Ignora scripts e styles
        if tag_name in ('script', 'style'):
            return
        
        # Títulos
        if tag_name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag_name[1])
            text = element.get_text(strip=True)
            if text:
                markdown_lines.append(f"\n{'#' * level} {text}\n")
            return
        
        # Parágrafos
        if tag_name == 'p':
            text = self._get_inline_text(element)
            if text:
                # Verifica se tem classe italic ou contém <em>
                classes = element.get('class', [])
                is_italic = 'italic' in classes or element.find('em')
                
                if is_italic and not text.startswith('*'):
                    markdown_lines.append(f"\n*{text}*\n")
                else:
                    markdown_lines.append(f"\n{text}\n")
            
            # Processa imagens dentro do parágrafo
            for img in element.find_all('img'):
                self._process_image_element(img, markdown_lines, base_url, headers, cookies, timeout)
            return
        
        # Blockquotes (cartas, citações)
        if tag_name == 'blockquote':
            texts = []
            for p in element.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    texts.append(text)
            
            if not texts:
                # Sem <p>, pega texto direto
                text = element.get_text(strip=True)
                if text:
                    texts = [text]
            
            if texts:
                markdown_lines.append("\n```")
                for text in texts:
                    markdown_lines.append(f"\n{text}\n")
                markdown_lines.append("```\n")
            return
        
        # Divs especiais (system-box, letter-box, etc.)
        if tag_name == 'div':
            classes = element.get('class', [])
            
            # Caixas de sistema ou cartas
            if any(c in classes for c in ('system-box', 'letter-box', 'box', 'notice')):
                texts = []
                for p in element.find_all('p'):
                    text = p.get_text(strip=True)
                    if text:
                        texts.append(text)
                
                if not texts:
                    text = element.get_text(strip=True)
                    if text:
                        texts = [text]
                
                if texts:
                    markdown_lines.append("\n```")
                    for text in texts:
                        markdown_lines.append(f"\n{text}")
                    markdown_lines.append("\n```\n")
                return
            
            # Div genérica - processa filhos
            for child in element.children:
                self._process_element(child, markdown_lines, base_url, headers, cookies, timeout, depth + 1)
            return
        
        # Imagens
        if tag_name == 'img':
            self._process_image_element(element, markdown_lines, base_url, headers, cookies, timeout)
            return
        
        # Figuras (imagens com caption)
        if tag_name == 'figure':
            img = element.find('img')
            if img:
                self._process_image_element(img, markdown_lines, base_url, headers, cookies, timeout)
            return
        
        # Separadores
        if tag_name == 'hr':
            markdown_lines.append("\n---\n")
            return
        
        # Listas
        if tag_name in ('ul', 'ol'):
            for i, li in enumerate(element.find_all('li', recursive=False)):
                text = li.get_text(strip=True)
                if text:
                    prefix = f"{i+1}." if tag_name == 'ol' else "-"
                    markdown_lines.append(f"\n{prefix} {text}")
            markdown_lines.append("\n")
            return
        
        # Containers genéricos (article, section, main) - processa filhos
        if tag_name in ('article', 'section', 'main', 'span'):
            for child in element.children:
                self._process_element(child, markdown_lines, base_url, headers, cookies, timeout, depth + 1)
            return
        
        # Outros elementos - tenta processar filhos
        for child in element.children:
            self._process_element(child, markdown_lines, base_url, headers, cookies, timeout, depth + 1)
    
    def _get_inline_text(self, element) -> str:
        """
        Extrai texto de um elemento preservando formatação inline (bold, italic)
        
        Args:
            element: Elemento BeautifulSoup
            
        Returns:
            str: Texto com formatação Markdown inline
        """
        result = []
        
        for child in element.children:
            if isinstance(child, NavigableString):
                result.append(str(child))
            elif isinstance(child, Tag):
                tag = child.name.lower() if child.name else ''
                text = child.get_text()
                
                if tag in ('strong', 'b'):
                    result.append(f"**{text}**")
                elif tag in ('em', 'i'):
                    result.append(f"*{text}*")
                elif tag == 'br':
                    result.append('\n')
                elif tag == 'img':
                    # Imagens são processadas separadamente
                    continue
                else:
                    result.append(text)
        
        text = ''.join(result)
        # Limpa espaços múltiplos mas preserva quebras de linha
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()
    
    def _process_image_element(self, img_element, markdown_lines: list, base_url: str,
                                headers=None, cookies=None, timeout=None):
        """
        Processa um elemento <img>, faz upload e adiciona ao Markdown
        
        Args:
            img_element: Elemento <img> BeautifulSoup
            markdown_lines: Lista para adicionar linha Markdown
            base_url: URL base para resolver URLs relativas
            headers, cookies, timeout: Parâmetros HTTP
        """
        img_url = img_element.get('src') or img_element.get('data-src')
        if not img_url:
            return
        
        # Resolve URL absoluta
        if base_url and not img_url.startswith(('http://', 'https://', 'data:')):
            img_url = urljoin(base_url, img_url)
        
        # Já é data URI - usa diretamente
        if img_url.startswith('data:'):
            img_alt = img_element.get('alt', 'Imagem')
            markdown_lines.append(f"\n![{img_alt}]({img_url})\n")
            return
        
        # Faz upload para CDN
        cdn_url = self._process_image(img_url, headers, cookies, timeout)
        if cdn_url:
            img_alt = img_element.get('alt', 'Imagem')
            markdown_lines.append(f"\n![{img_alt}]({cdn_url})\n")
    
    def _process_image(self, url: str, headers=None, cookies=None, timeout=None) -> Optional[str]:
        """
        Processa uma imagem: faz upload para CDN ou converte para base64
        
        Args:
            url: URL da imagem
            headers: Headers HTTP
            cookies: Cookies HTTP
            timeout: Timeout da requisição
        
        Returns:
            str: URL do CDN ou Data URI base64
        """
        try:

            try:
                response = Http.get(url, headers=headers, cookies=cookies, timeout=timeout)
            except Exception as e2:
                print(f"[Download] Falha com Http para {url}: {e2}")

            # response = Http.get(url, headers=headers, cookies=cookies, timeout=timeout)
            
            # Detecta extensão
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp',
                '.svg': 'image/svg+xml'
            }
            
            mime_type = 'image/jpeg'
            extensao = 'jpg'
            for ext, mime in mime_types.items():
                if path.endswith(ext):
                    mime_type = mime
                    extensao = ext.lstrip('.')
                    break
            
            # Fallback: base64
            base64_data = base64.b64encode(response.content).decode('utf-8')
            data_uri = f"data:{mime_type};base64,{base64_data}"
            print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:blue;'>Image embedded</span> {url}")
            return data_uri
            
        except Exception as e:
            print(f"<stroke style='color:green;'>[Downloading]:</stroke> <span style='color:red;'>Image error</span> {url}: {e}")
            return None
