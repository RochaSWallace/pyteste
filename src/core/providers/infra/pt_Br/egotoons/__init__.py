from core.providers.infra.template.yushuke_theme import YushukeTheme
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from html import unescape
import json
import re
import time

class EgoToonsProvider(YushukeTheme):
    name = 'Ego Toons'
    lang = 'pt_Br'
    domain = ['egotoons.com']

    def __init__(self) -> None:
        self.url = 'https://egotoons.com'
        self.chapters_api = f'{self.url}/ajax/lzmvke.php?'
        
        self.title = 'div.data-v-04d59791 h1'
        self.manga_id_selector = "button#CarregarCapitulos"
        self.chapter_item_selector = 'a.chapter-item'
        self.chapter_number_selector = 'span.capitulo-numero'
        self.chapter_views_selector = 'span.chapter-views'
        self.id_manga = 'data-manga-id'
        self.pages_selector = "ul.flex.flex-col.justify-center.items-center li"
        self.image_selector = "img"

    def _fix_json_string(self, json_str: str) -> str:
        """Corrige JSON com quebras de linha problemáticas"""
        
        # ✅ MÉTODO 1: Corrige quebras de linha específicas na description
        pattern_desc = r'("description":\s*")(.*?)("(?=\s*,))'
        
        def fix_description(match):
            prefix = match.group(1)
            content = match.group(2)
            suffix = match.group(3)
            
            # Remove quebras de linha e escapa aspas internas
            content = content.replace('\n', ' ').replace('\r', ' ')
            content = re.sub(r'\s+', ' ', content)  # Múltiplos espaços -> um espaço
            content = content.replace('"', '\\"')   # Escapa aspas internas
            
            return f"{prefix}{content}{suffix}"
        
        json_str = re.sub(pattern_desc, fix_description, json_str, flags=re.DOTALL)
        
        # ✅ MÉTODO 2: Remove quebras de linha restantes
        json_str = re.sub(r'\n\s*', ' ', json_str)
        json_str = re.sub(r'\s+', ' ', json_str)
        
        return json_str.strip()

    def _decode_unicode_escapes(self, text: str) -> str:
        """Decodifica escapes unicode de forma segura e automática"""
        if not text:
            return text
        
        try:
            # Método 1: Decodificação nativa (mais eficiente)
            return text.encode().decode('unicode_escape')
        except (UnicodeDecodeError, UnicodeEncodeError):
            try:
                # Método 2: Codecs para casos específicos
                import codecs
                return codecs.decode(text, 'unicode_escape')
            except:
                # Método 3: Fallback manual para casos comuns
                replacements = {
                    '\\u00e1': 'á', '\\u00e9': 'é', '\\u00ed': 'í', '\\u00f3': 'ó', '\\u00fa': 'ú',
                    '\\u00e0': 'à', '\\u00e8': 'è', '\\u00ec': 'ì', '\\u00f2': 'ò', '\\u00f9': 'ù',
                    '\\u00e2': 'â', '\\u00ea': 'ê', '\\u00ee': 'î', '\\u00f4': 'ô', '\\u00fb': 'û',
                    '\\u00e3': 'ã', '\\u00f5': 'õ', '\\u00e7': 'ç', '\\u00f1': 'ñ',
                    '\\u00c1': 'Á', '\\u00c9': 'É', '\\u00cd': 'Í', '\\u00d3': 'Ó', '\\u00da': 'Ú',
                    '\\u00c0': 'À', '\\u00c8': 'È', '\\u00cc': 'Ì', '\\u00d2': 'Ò', '\\u00d9': 'Ù',
                    '\\u00c2': 'Â', '\\u00ca': 'Ê', '\\u00ce': 'Î', '\\u00d4': 'Ô', '\\u00db': 'Û',
                    '\\u00c3': 'Ã', '\\u00d5': 'Õ', '\\u00c7': 'Ç', '\\u00d1': 'Ñ'
                }
                
                result = text
                for unicode_char, normal_char in replacements.items():
                    result = result.replace(unicode_char, normal_char)
                return result

    def getManga(self, link: str) -> Manga:
        response = Http.get(link)
        if hasattr(response, 'text'):
            if callable(response.text):
                html = response.text()
            else:
                html = response.text
        else:
            html = str(response.content, 'utf-8')

        clean_html = unescape(html)
        pattern = r'"comic_infos":\s*(\{.*?"chapters":\s*\[.*?\]\s*\})'
        matches = re.findall(pattern, clean_html, re.DOTALL)
        
        if matches:
            try:
                json_str = matches[0]
                
                fixed_json = self._fix_json_string(json_str)
                
                comic_data = json.loads(fixed_json)
                title = comic_data.get('title', 'Título Desconhecido')
                
                # ✅ Decodifica caracteres unicode automaticamente
                title = self._decode_unicode_escapes(title)
                
                return Manga(link, title.strip())
                
            except json.JSONDecodeError as e:
                print(f"❌ Erro JSON: {e}")
                print(f"Char {e.pos}: '{fixed_json[e.pos-5:e.pos+5]}'")
                
                # FALLBACK: extração manual do título
                title_match = re.search(r'"title":\s*"([^"]+)"', json_str)
                if title_match:
                    title = title_match.group(1)
                    title = self._decode_unicode_escapes(title)
                    return Manga(link, title.strip())
                
                return Manga(link, "Erro no JSON")
        
        return Manga(link, "JSON não encontrado")

    def getChapters(self, id: str) -> List[Chapter]:
        response = Http.get(id)
        if hasattr(response, 'text'):
            if callable(response.text):
                html = response.text()
            else:
                html = response.text
        else:
            html = str(response.content, 'utf-8')

        # Decodifica HTML entities
        clean_html = unescape(html)
        chapter_list = []
        
        # Padrão específico para dados do comic no EgoToons
        pattern = r'"comic_infos":\s*(\{.*?"chapters":\s*\[.*?\]\s*\})'
        
        matches = re.findall(pattern, clean_html, re.DOTALL)
        
        if matches:
            try:
                # Pega o primeiro match
                json_str = matches[0]
                
                # ✅ USA MÉTODO DE CORREÇÃO ROBUSTO (mesmo do getManga)
                fixed_json = self._fix_json_string(json_str)
                
                comic_data = json.loads(fixed_json)
                title = comic_data.get('title', 'Título Desconhecido')
                title = self._decode_unicode_escapes(title)
                chapters = comic_data.get('chapters', [])
                
                for chapter in chapters:
                    chapter_url = chapter.get('chapter_path')
                    if not chapter_url.startswith('http'):
                        chapter_url = f'{self.url}/chapter/{chapter_url}'
                    else:
                        chapter_url = chapter.get('url')
                        
                    chapter_number = chapter.get('chapter_number', 'Capítulo Desconhecido')
                    
                    chapter_list.append(Chapter(
                        chapter_url,
                        str(chapter_number),
                        title
                    ))
                    
            except json.JSONDecodeError as e:
                print(f"❌ Erro JSON no getChapters: {e}")
                print(f"Char {e.pos}: '{fixed_json[e.pos-5:e.pos+5] if e.pos < len(fixed_json) else 'EOF'}'")
                
                # FALLBACK: Tenta extrair capítulos manualmente usando regex
                try:
                    chapters_match = re.search(r'"chapters":\s*\[(.*?)\]', json_str, re.DOTALL)
                    if chapters_match:
                        print("Tentando extrair capítulos com fallback...")
                        # Implementar fallback se necessário
                except Exception as fallback_error:
                    print(f"Fallback também falhou: {fallback_error}")
                
                return []
        
        return chapter_list

    def getPages(self, ch: Chapter) -> Pages:
        # Configurações do Chrome
        options = Options()
        options.add_argument('--headless')  # Remove para ver a janela do navegador
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        driver = webdriver.Chrome(options=options)
        
        try:
            driver.get(ch.id)
            # time.sleep(2)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')     
        finally:
            driver.quit()
        
        images = []
        picture_elements = soup.select(self.pages_selector)
        for index, picture_element in enumerate(picture_elements):
            img_element = picture_element.select_one(self.image_selector)
            if img_element and img_element.get('src'):
                image_url = img_element.get('src')
                if image_url.strip():
                    images.append(image_url)
        return Pages(ch.id, ch.number, ch.name, images)