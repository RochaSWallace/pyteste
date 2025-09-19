import os
import cv2
import base64
import time
import re
import threading
import atexit
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import urljoin
from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Pages, Manga
from core.download.application.use_cases import DownloadUseCase
from core.providers.infra.template.wordpress_madara import WordPressMadara
from DrissionPage import ChromiumPage, ChromiumOptions

# Variável global para controlar se login já foi verificado
_MANHASTRO_LOGIN_CHECKED = False

# Sistema de navegador compartilhado com múltiplas abas
_SHARED_BROWSER = None
_BROWSER_LOCK = threading.Lock()

def _get_shared_browser():
    """Pega o navegador compartilhado ou cria um novo"""
    global _SHARED_BROWSER
    with _BROWSER_LOCK:
        if _SHARED_BROWSER is None:
            options = ChromiumOptions()
            options.headless(True)
            options.set_argument('--no-sandbox')
            options.set_argument('--disable-dev-shm-usage')
            options.set_argument('--disable-gpu')
            options.set_argument('--disable-extensions')
            options.set_argument('--disable-web-security')
            _SHARED_BROWSER = ChromiumPage(options)
            print("Navegador compartilhado criado")
        return _SHARED_BROWSER

def _cleanup_shared_browser():
    """Fecha o navegador compartilhado"""
    global _SHARED_BROWSER
    with _BROWSER_LOCK:
        if _SHARED_BROWSER:
            try:
                _SHARED_BROWSER.quit()
                print("Navegador compartilhado fechado")
            except:
                pass
            _SHARED_BROWSER = None

# Registrar cleanup no exit
atexit.register(_cleanup_shared_browser)

def _check_manhastro_login():
    """Verifica login do Manhastro apenas uma vez por execução"""
    global _MANHASTRO_LOGIN_CHECKED
    if _MANHASTRO_LOGIN_CHECKED:
        return
    
    page = ChromiumPage()
    try:
        page.get('https://manhastro.net/')
        time.sleep(30)
    finally:
        page.quit()
        _MANHASTRO_LOGIN_CHECKED = True

class ManhastroProvider(WordPressMadara):
    name = 'Manhastro'
    lang = 'pt-Br'
    domain = ['manhastro.net']

    def __init__(self):
        self.url = 'https://manhastro.net/'
        self.path = ''
        
        # Verifica login antes de começar
        _check_manhastro_login()
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'div.relative > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'img[alt*="Página"]'
        self.query_title_for_uri = 'div.space-y-4 > h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'

    def getManga(self, link: str) -> Manga:
        try:
            browser = _get_shared_browser()
            tab = browser.new_tab()
            
            tab.get(link)
            time.sleep(3)  # Aguarda carregamento
            response = tab.html
            soup = BeautifulSoup(response, 'html.parser')
            
            # Tenta múltiplos seletores para maior compatibilidade
            data = soup.select(self.query_title_for_uri)           
            element = data.pop()
            title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
                
            print(f"Título encontrado: {title}")
            return Manga(id=link, name=title)
            
        except Exception as e:
            print(f"Erro ao obter manga: {e}")
            raise
        finally:
            try:
                tab.close()
            except:
                pass
    
    def getChapters(self, id: str) -> List[Chapter]:
        try:
            browser = _get_shared_browser()
            tab = browser.new_tab()
            
            uri = urljoin(self.url, id)
            tab.get(uri)
            time.sleep(2)
            
            response = tab.html
            soup = BeautifulSoup(response, 'html.parser')
            data = soup.select(self.query_title_for_uri)
            element = data.pop()
            title = element['content'].strip() if 'content' in element.attrs else element.text.strip()
            dom = soup.select('body')[0]
            data = dom.select(self.query_chapters)

            chs = []
            for el in data:
                ch_id = self.get_root_relative_or_absolute_link(el, uri)
                # Busca especificamente pelo span que contém o nome do capítulo
                chapter_span = el.select_one('span.text-white')
                if chapter_span:
                    ch_number = chapter_span.text.strip()
                else:
                    # Fallback: pega o primeiro texto encontrado no elemento
                    ch_number = el.text.strip().split('\n')[0].strip()
                ch_name = title
                chs.append(Chapter(ch_id, ch_number, ch_name))

            chs.reverse()
            return chs
        except Exception as e:
            print(f"Erro ao obter capítulos: {e}")
            return []
        finally:
            try:
                tab.close()
            except:
                pass

    def getPages(self, ch: Chapter) -> Pages:
        """Pega páginas usando aba compartilhada no navegador principal com retry"""
        browser = _get_shared_browser()
        max_retries = 10
        
        for attempt in range(max_retries):
            new_tab = None
            try:
                # Criar nova aba para esta requisição
                new_tab = browser.new_tab()
                
                uri = urljoin(self.url, ch.id)
                print(f"Tentativa {attempt + 1}/{max_retries} - Buscando páginas para: {ch.name}")
                
                new_tab.get(uri)
                time.sleep(2*(attempt+1))  # Espera progressiva
                
                # Usar a nova aba para extrair dados
                response = new_tab.html
                soup = BeautifulSoup(response, 'html.parser')
                data = soup.select(self.query_pages)
                
                pages_list = [] 
                for el in data:
                    src = el.get("src")
                    if src:
                        pages_list.append(src)

                # Se encontrou páginas, retorna sucesso
                if pages_list:
                    number = re.findall(r'\d+\.?\d*', str(ch.number))[0]
                    print(f"✅ Sucesso: {len(pages_list)} páginas para {ch.name}")
                    return Pages(ch.id, number, ch.name, pages_list)
                else:
                    print(f"⚠️ Tentativa {attempt + 1}: Nenhuma página encontrada para {ch.name}")
                    
            except Exception as e:
                print(f"❌ Tentativa {attempt + 1} falhou para {ch.name}: {e}")
                
            finally:
                # Fechar aba da tentativa atual
                if new_tab:
                    try:
                        new_tab.close()
                        print(f"Aba fechada (tentativa {attempt + 1})")
                    except Exception as e:
                        print(f"Erro ao fechar aba: {e}")
            
            # Se não é a última tentativa, aguarda antes de tentar novamente
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s progressivamente
                time.sleep(wait_time)
        
        # Se chegou aqui, todas as tentativas falharam
        print(f"💥 Todas as {max_retries} tentativas falharam para {ch.name}")
        return Pages(ch.id, ch.number, ch.name, [])
    
    def adjust_template_size(self, template, img):
        try:
            if template is None or img is None:
                return None
                
            h_img, w_img = img.shape[:2]
            h_template, w_template = template.shape[:2]
            
            if h_template <= 0 or w_template <= 0 or h_img <= 0 or w_img <= 0:
                return None

            if h_template > h_img or w_template > w_img:
                scale_h = h_img / h_template
                scale_w = w_img / w_template
                scale = min(scale_h, scale_w)
                
                new_width = max(1, int(w_template * scale))
                new_height = max(1, int(h_template * scale))
                
                template = cv2.resize(template, (new_width, new_height))
                
                if template is None or template.shape[0] == 0 or template.shape[1] == 0:
                    return None

            return template
        
        except Exception as e:
            print(f"❌ Erro ao ajustar tamanho do template: {e}")
            return None
    
    def removeMark(self, img_path, template_path, output_path) -> bool:
        try:
            if not os.path.exists(img_path):
                print(f"❌ Imagem não encontrada: {img_path}")
                return False
                
            if not os.path.exists(template_path):
                print(f"❌ Template não encontrado: {template_path}")
                return False
            
            try:
                import numpy as np
                with open(img_path, 'rb') as f:
                    file_bytes = np.asarray(bytearray(f.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"❌ Erro ao carregar imagem com numpy: {e}")
                img = cv2.imread(img_path)
            
            if img is None:
                print(f"❌ Erro ao carregar imagem: {img_path}")
                return False
            
            try:
                import numpy as np
                with open(template_path, 'rb') as f:
                    template_bytes = np.asarray(bytearray(f.read()), dtype=np.uint8)
                template = cv2.imdecode(template_bytes, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"❌ Erro ao carregar template com numpy: {e}")
                template = cv2.imread(template_path)
            
            if template is None:
                print(f"❌ Erro ao carregar template: {template_path}")
                return False
            
            if img.shape[0] == 0 or img.shape[1] == 0:
                print(f"❌ Imagem com dimensões inválidas: {img_path}")
                return False
                
            if template.shape[0] == 0 or template.shape[1] == 0:
                print(f"❌ Template com dimensões inválidas: {template_path}")
                return False
            
            template = self.adjust_template_size(template, img)
            
            if template is None or template.shape[0] == 0 or template.shape[1] == 0:
                print(f"❌ Template inválido após redimensionamento")
                return False

            h, w = template.shape[:2]
            
            if img.shape[0] < h or img.shape[1] < w:
                print(f"❌ Imagem muito pequena para o template. Img: {img.shape[:2]}, Template: {h}x{w}")
                return False

            img_cropped = img[-h:, :]

            # Template matching
            result = cv2.matchTemplate(img_cropped, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= 0.8:
                img_without_mark = img[:-h, :]
                
                try:
                    is_success, buffer = cv2.imencode(".jpg", img_without_mark)
                    if is_success:
                        with open(output_path, 'wb') as f:
                            f.write(buffer)
                        print(f"✅ Marca d'água removida: {os.path.basename(output_path)}")
                        return True
                    else:
                        print(f"❌ Erro ao codificar imagem processada")
                        return False
                except Exception as e:
                    print(f"❌ Erro ao salvar imagem processada: {e}")
                    return False
            # else:
            #    print(f"⚠️ Marca d'água não detectada (confiança: {max_val:.2%})")
            
            return False
            
        except Exception as e:
            print(f"❌ Erro no processamento de marca d'água: {e}")
            print(f"   Imagem: {img_path}")
            print(f"   Template: {template_path}")
            return False
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        pages = DownloadUseCase().execute(pages=pages, fn=fn, headers=headers, cookies=cookies)
        marks = ['mark.jpg', 'mark2.jpg', 'mark3.jpg', 'mark4.jpg', 'mark5.jpg', 'mark6.jpg', 'mark7.jpg', 'mark8.jpg', 'mark9.jpg', 'mark10.jpg', 'mark11.jpg', 'mark12.jpg', 'mark13.jpg']
        temp_page = sorted(pages.files)
        for page in temp_page[-2:]:
            print(f'Removendo marca d\'água de: {page}')
            for mark in marks:
                if self.removeMark(page, os.path.join(Path(__file__).parent, mark), page):
                    break
        return  pages
