"""
Provider para GeassComics (https://geasscomics.xyz/)
Site com React/JavaScript que requer Selenium para extração de capítulos com AWS S3 CDN
"""

import re
import time
import json
import os
import math
import base64
import requests
import cv2
import numpy as np
from pathlib import Path
from typing import List
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from core.download.domain.dowload_entity import Chapter as DownloadedChapter
from core.config.img_conf import get_config
from core.__seedwork.infra.utils.sanitize_folder import sanitize_folder_name
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
import httpx

class GeassComicsProvider(Base):
    name = 'Geass Comics'
    lang = 'pt_Br'
    domain = ['geasscomics.xyz']

    def __init__(self) -> None:
        self.url = 'https://geasscomics.xyz'
        self.timeout = 20
        self.max_paginas = 50

    def _configurar_selenium(self, headless: bool = True):
        """Configura o Selenium com opções otimizadas"""
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        driver = webdriver.Chrome(options=options)
        return driver

    def _is_placeholder_image(self, img_path: str) -> bool:
        """
        Detecta se uma imagem é placeholder (geass1.png ou geass2.png)
        usando template matching (similar ao Manhastro)
        """
        try:
            if not os.path.exists(img_path):
                return False
            
            # Carrega imagem a verificar
            img = cv2.imread(img_path)
            if img is None:
                return False
            
            # Templates dos placeholders
            placeholders = ['geas_1.jpg', 'geas_2.jpg']
            
            for placeholder in placeholders:
                template_path = os.path.join(Path(__file__).parent, placeholder)
                
                if not os.path.exists(template_path):
                    continue
                
                template = cv2.imread(template_path)
                if template is None:
                    continue
                
                # Verifica se template é maior que imagem
                if template.shape[0] > img.shape[0] or template.shape[1] > img.shape[1]:
                    continue
                
                # Template matching
                result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                # Se confiança >= 90%, é placeholder
                if max_val >= 0.90:
                    print(f"  ⚠ Placeholder detectado: {os.path.basename(placeholder)} (confiança: {max_val:.2%})")
                    return True
            
            return False
            
        except Exception as e:
            print(f"  ✗ Erro ao verificar placeholder: {e}")
            return False

    def _extrair_capitulos_pagina(self, soup, obra_id: int):
        """Extrai capítulos de uma página já parseada"""
        capitulos = []
        
        # Procura pelos links de capítulos
        padrao = re.compile(rf'/obra/{obra_id}/capitulo/(\d+)')
        links = soup.find_all('a', href=padrao)
        
        for link in links:
            href = link.get('href', '')
            match = padrao.search(href)
            
            if match:
                numero = int(match.group(1))
                
                # Extrai nome do capítulo
                h3 = link.find('h3')
                nome = h3.get_text(strip=True) if h3 else f"Capítulo {numero}"
                
                capitulo = {
                    'numero': numero,
                    'nome': nome,
                    'href': href,
                    'url_completa': f"{self.url}{href}"
                }
                
                capitulos.append(capitulo)
        
        return capitulos

    def _verificar_botao_proxima_pagina(self, driver):
        """Verifica se existe botão de próxima página e clica nele"""
        try:
            # Verifica indicador de página
            try:
                indicador = driver.find_element(By.CSS_SELECTOR, 'span.text-sm')
                texto = indicador.text
                if '/' in texto:
                    pagina_atual, total_paginas = map(int, texto.split('/'))
                    print(f"[GeassComics] Página {pagina_atual}/{total_paginas}")
                    
                    if pagina_atual >= total_paginas:
                        return False
            except:
                pass
            
            # Procura pelo botão "Próxima página"
            try:
                botao_proxima = driver.find_element(By.CSS_SELECTOR, 'button[title="Próxima página"]')
                if botao_proxima.is_enabled() and botao_proxima.is_displayed():
                    disabled = botao_proxima.get_attribute('disabled')
                    if not disabled:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_proxima)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", botao_proxima)
                        return True
            except:
                pass
            
            # Procura por botão com SVG chevron-right
            try:
                chevron_right = driver.find_elements(By.CSS_SELECTOR, 'svg.lucide-chevron-right')
                for svg in chevron_right:
                    botao = svg.find_element(By.XPATH, '..')
                    if botao.tag_name == 'button':
                        disabled = botao.get_attribute('disabled')
                        if not disabled and botao.is_enabled() and botao.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", botao)
                            return True
            except:
                pass
            
            return False
            
        except Exception as e:
            print(f"[GeassComics] Erro ao verificar próxima página: {e}")
            return False

    def getManga(self, link: str) -> Manga:
        """Extrai informações básicas da obra"""
        try:
            # Extrai ID da obra da URL
            match = re.search(r'/obra/(\d+)', link)
            if not match:
                raise Exception("ID da obra não encontrado na URL")
            
            obra_id = int(match.group(1))
            
            print(f"[GeassComics] Acessando obra: {link}")
            
            driver = self._configurar_selenium(headless=True)
            
            try:
                driver.get(link)
                wait = WebDriverWait(driver, self.timeout)
                
                # Espera skeleton desaparecer
                try:
                    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "animate-pulse")))
                except:
                    pass
                
                time.sleep(2)
                
                # Extrai título
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                # Procura por h1 ou h2 com título
                title_elem = soup.find('h1') or soup.find('h2')
                title = title_elem.get_text(strip=True) if title_elem else f"Obra {obra_id}"
                
                print(f"[GeassComics] Título: {title}")
                
                return Manga(link, title)
                
            finally:
                driver.quit()
                
        except Exception as e:
            print(f"[GeassComics] Erro em getManga: {e}")
            raise

    def getChapters(self, manga_id: str) -> List[Chapter]:
        """Extrai todos os capítulos navegando por todas as páginas"""
        try:
            # Extrai ID da obra
            match = re.search(r'/obra/(\d+)', manga_id)
            if not match:
                raise Exception("ID da obra não encontrado")
            
            obra_id = int(match.group(1))
            url = f"{self.url}/obra/{obra_id}"
            
            print(f"[GeassComics] Extraindo capítulos de: {url}")
            
            driver = self._configurar_selenium(headless=True)
            todos_capitulos = []
            pagina_atual = 1
            
            try:
                driver.get(url)
                wait = WebDriverWait(driver, self.timeout)
                
                # Espera skeleton desaparecer
                try:
                    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "animate-pulse")))
                except:
                    pass
                
                # Loop para varrer todas as páginas
                while pagina_atual <= self.max_paginas:
                    print(f"[GeassComics] Processando página {pagina_atual}")
                    
                    # Espera capítulos carregarem
                    try:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"a[href*='/obra/{obra_id}/capitulo/']")))
                    except:
                        pass
                    
                    # time.sleep(0.5)
                    
                    # Extrai capítulos da página atual
                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    capitulos_pagina = self._extrair_capitulos_pagina(soup, obra_id)
                    
                    print(f"[GeassComics] {len(capitulos_pagina)} capítulos na página {pagina_atual}")
                    
                    if capitulos_pagina:
                        todos_capitulos.extend(capitulos_pagina)
                    else:
                        break
                    
                    # Tenta ir para próxima página
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    tem_proxima = self._verificar_botao_proxima_pagina(driver)
                    
                    if not tem_proxima:
                        print(f"[GeassComics] Última página alcançada")
                        break
                    
                    # Espera nova página carregar
                    # time.sleep(0.5)
                    
                    try:
                        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "animate-pulse")))
                    except:
                        pass
                    
                    pagina_atual += 1
                
                # Remove duplicatas e converte para Chapter
                capitulos_unicos = {cap['numero']: cap for cap in todos_capitulos}
                capitulos_finais = sorted(capitulos_unicos.values(), key=lambda x: x['numero'])
                
                print(f"[GeassComics] ✓ {len(capitulos_finais)} capítulos únicos extraídos")
                
                # Extrai título da obra
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                title_elem = soup.find('h1') or soup.find('h2')
                manga_title = title_elem.get_text(strip=True) if title_elem else f"Obra {obra_id}"
                
                # Converte para objetos Chapter
                chapters_list = []
                for cap in capitulos_finais:
                    chapters_list.append(
                        Chapter(
                            cap['url_completa'],
                            str(cap['numero']),
                            manga_title
                        )
                    )
                # Chapter(link, number_element.get_text().strip(), title)
                return chapters_list
                
            finally:
                driver.quit()
                
        except Exception as e:
            print(f"[GeassComics] Erro em getChapters: {e}")
            return []

    def getPages(self, ch: Chapter) -> Pages:
        """Extrai URLs das páginas de um capítulo via POST request"""
        try:
            print(f"[GeassComics] Extraindo páginas: {ch.name}")
            
            # Extrai obra_id e capitulo_numero da URL
            # Formato: https://geasscomics.xyz/obra/274/capitulo/174
            match = re.search(r'/obra/(\d+)/capitulo/(\d+)', ch.id)
            if not match:
                raise Exception("IDs não encontrados na URL do capítulo")
            
            obra_id = int(match.group(1))
            capitulo_numero = int(match.group(2))
            
            print(f"[GeassComics] Obra ID: {obra_id}, Capítulo: {capitulo_numero}")
            
            # Monta a requisição POST
            url = ch.id
            headers = {
                "accept": "text/x-component",
                "accept-language": "pt-BR,pt;q=0.5",
                "content-type": "text/plain;charset=UTF-8",
                "next-action": "60d114b5ac9241ed3aef928677c0ead8e90523568a",
                "next-router-state-tree": f'%5B%22%22%2C%7B%22children%22%3A%5B%22obra%22%2C%7B%22children%22%3A%5B%5B%22id%22%2C%22{obra_id}%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22capitulo%22%2C%7B%22children%22%3A%5B%5B%22numero%22%2C%22{capitulo_numero}%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
                "priority": "u=1, i",
                "sec-ch-ua": '"Chromium";v="142", "Brave";v="142", "Not_A Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "sec-gpc": "1",
                "referer": ch.id,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            body = f"[{obra_id},{capitulo_numero}]"
            
            # Realiza o POST
            response = requests.post(url, headers=headers, data=body, timeout=30)
            response.raise_for_status()
            
            # A resposta vem em formato especial, precisa parsear
            # Exemplo: 0:{...}\n1:{"success":true,"images":[...]}
            response_text = response.text
            print(f"[GeassComics] Resposta recebida ({len(response_text)} bytes)")
            
            # Procura pela linha que contém "images"
            images = []
            for line in response_text.split('\n'):
                if '"images"' in line:
                    # Extrai o JSON da linha
                    # Remove o prefixo "1:" ou similar
                    json_match = re.search(r'^\d+:(.+)$', line)
                    if json_match:
                        json_str = json_match.group(1)
                        data = json.loads(json_str)
                        
                        if data.get('success') and 'images' in data:
                            images = data['images']
                            break
     
            if not images:
                # Fallback: tenta extrair diretamente com regex
                images_match = re.search(r'"images":\s*(\[.+?\])', response_text, re.DOTALL)
                if images_match:
                    images = json.loads(images_match.group(1))
            
            print(f"[GeassComics] ✓ {len(images)} páginas encontradas")
            
            # Adiciona o referrer (ch.id) como prefixo em cada URL
            # Formato: "REFERRER|URL_DA_IMAGEM"
            images_with_referrer = [f"{ch.id}|{img_url}" for img_url in images]
            
            return Pages(ch.id, ch.number, ch.name, images_with_referrer)
                
        except Exception as e:
            print(f"[GeassComics] Erro em getPages: {e}")
            import traceback
            traceback.print_exc()
            return Pages(ch.id, ch.number, ch.name, [])
    
    def _download_usando_selenium_fetch(self, pages: Pages, images: list, fn: any, path: str, img_format: str, total_pages: int):
        """
        Navega para a página do capítulo e extrai as imagens já renderizadas.
        Filtra imagens de placeholder (geass1.png).
        """
        temp_files = []
        
        try:
            driver = self._configurar_selenium()
            
            # Extrai IDs e navega para a página
            match = re.search(r'/obra/(\d+)/capitulo/(\d+)', pages.id)
            if not match:
                return DownloadedChapter(pages.number, temp_files)
            
            capitulo_url = f"https://geasscomics.xyz/obra/{match.group(1)}/capitulo/{match.group(2)}"
            driver.get(capitulo_url)
            time.sleep(5)  # Aguarda JavaScript carregar
            
            # EXTRAI TODOS OS CANVAS/IMAGENS DE UMA VEZ
            all_images = driver.execute_script('''
                const result = [];
                
                // 1. Tenta extrair de CANVAS
                const canvases = document.querySelectorAll('canvas');
                for (let canvas of canvases) {
                    if (canvas.width > 0 && canvas.height > 0) {
                        try {
                            const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
                            result.push({ source: 'canvas', data: dataUrl });
                        } catch(e) {
                            console.log('Erro ao extrair canvas:', e);
                        }
                    }
                }
                
                // 2. Se não tem canvas, tenta extrair de IMG
                if (result.length === 0) {
                    const imgs = document.querySelectorAll('img');
                    for (let img of imgs) {
                        // FILTRA geass1.png (placeholder/watermark)
                        if (img.src && !img.src.includes('geass1.png')) {
                            if (img.src.includes('cdn.mymangas.com.br') || img.src.includes('geasscomics.xyz/api/cdn')) {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                const ctx = canvas.getContext('2d');
                                try {
                                    ctx.drawImage(img, 0, 0);
                                    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
                                    result.push({ source: 'img', data: dataUrl });
                                } catch(e) {
                                    console.log('Erro ao extrair img:', e);
                                }
                            }
                        }
                    }
                }
                
                return result;
            ''')
            
            if not all_images:
                print(f"[GeassComics] ✗ Nenhuma imagem encontrada na página")
                driver.quit()
                return DownloadedChapter(pages.number, temp_files)
            
            print(f"[GeassComics] ✓ {len(all_images)} imagens encontradas na página")
            
            # BAIXA TODAS AS IMAGENS ENCONTRADAS
            all_saved_files = []  # Lista com TODAS as imagens (incluindo placeholders)
            
            for idx, img_obj in enumerate(all_images, start=1):
                try:
                    print(f"[GeassComics] [{idx}/{len(all_images)}] Salvando imagem...")
                    
                    canvas_data = img_obj.get('data')
                    if not canvas_data or not canvas_data.startswith('data:'):
                        print(f"  ✗ Dados inválidos")
                        continue
                    
                    # Decodifica Base64 e salva
                    base64_data = canvas_data.split(',')[1]
                    img_data = base64.b64decode(base64_data)
                    
                    img = Image.open(BytesIO(img_data))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    file_path = os.path.join(path, f"temp_%03d{img_format}" % idx)
                    img.save(file_path, quality=100, dpi=(72, 72))
                    all_saved_files.append(file_path)
                    
                    print(f"  ✓ Salvo: {os.path.basename(file_path)}")
                        
                except Exception as e:
                    print(f"  ✗ Erro: {e}")
                    continue
            
            driver.quit()
            
            # FILTRA PLACEHOLDERS e RENOMEIA
            print(f"[GeassComics] Verificando placeholders...")
            valid_idx = 1
            
            for temp_file in all_saved_files:
                if self._is_placeholder_image(temp_file):
                    # Remove placeholder
                    os.remove(temp_file)
                    print(f"  ✗ Removido: {os.path.basename(temp_file)}")
                else:
                    # Renomeia para numeração correta
                    final_path = os.path.join(path, f"%03d{img_format}" % valid_idx)
                    os.rename(temp_file, final_path)
                    temp_files.append(final_path)
                    valid_idx += 1
            
        except Exception as e:
            print(f"[GeassComics] ✗ Erro: {e}")
        
        print(f"[GeassComics] Selenium: {len(temp_files)} imagens válidas extraídas")
        return DownloadedChapter(pages.number, temp_files)
    
    def download(self, pages: Pages, fn: any, headers=None, cookies=None):
        """
        Download de imagens do GeassComics.
        Suporta dois tipos de CDN: API interna (requests) e AWS S3 (Selenium).
        """
        title = sanitize_folder_name(pages.name)
        config = get_config()
        img_path = config.save
        path = os.path.join(img_path, str(title), str(sanitize_folder_name(pages.number)))
        os.makedirs(path, exist_ok=True)
        img_format = config.img

        files = []
        total_pages = len(pages.pages)
        
        # Extrai obra_id e capitulo_numero da URL
        match = re.search(r'/obra/(\d+)/capitulo/(\d+)', pages.id)
        if not match:
            print(f"[GeassComics] ✗ Erro: Não foi possível extrair IDs da URL")
            return DownloadedChapter(pages.number, files)
        
        obra_id = int(match.group(1))
        capitulo_numero = int(match.group(2))
        
        try:
            # FAZ POST PARA OBTER URLs DAS IMAGENS
            url = pages.id
            headers_post = {
                "accept": "text/x-component",
                "content-type": "text/plain;charset=UTF-8",
                "next-action": "60d114b5ac9241ed3aef928677c0ead8e90523568a",
                "next-router-state-tree": f'%5B%22%22%2C%7B%22children%22%3A%5B%22obra%22%2C%7B%22children%22%3A%5B%5B%22id%22%2C%22{obra_id}%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22capitulo%22%2C%7B%22children%22%3A%5B%5B%22numero%22%2C%22{capitulo_numero}%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
                "referer": pages.id,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            body = f"[{obra_id},{capitulo_numero}]"
            response = requests.post(url, headers=headers_post, data=body, timeout=30)
            response.raise_for_status()
            
            # Parse das URLs
            images = []
            for line in response.text.split('\n'):
                if '"images"' in line:
                    json_match = re.search(r'^\d+:(.+)$', line)
                    if json_match:
                        data = json.loads(json_match.group(1))
                        if data.get('success') and 'images' in data:
                            images = data['images']
                            break
            
            if not images:
                raise Exception("Nenhuma imagem retornada no POST")
            
            # DETECTA TIPO DE CDN
            first_url = images[0] if images else ""
            is_s3_cdn = "X-Amz-" in first_url or "cdn.mymangas.com.br" in first_url
            
            if is_s3_cdn:
                # AWS S3 CDN - usa Selenium (navega na página e extrai canvas)
                return self._download_usando_selenium_fetch(pages, images, fn, path, img_format, total_pages)
            
            # API INTERNA - usa requests direto
            temp_files = []
            
            for idx, img_url in enumerate(images, start=1):
                try:
                    print(f"[GeassComics] [{idx}/{total_pages}] Baixando...")
                    
                    # Headers mínimos
                    download_headers = {
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                    
                    response_img = requests.get(img_url, headers=download_headers, timeout=30)
                    response_img.raise_for_status()
                    
                    # Salva imagem
                    img = Image.open(BytesIO(response_img.content))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    file_path = os.path.join(path, f"%03d{img_format}" % idx)
                    img.save(file_path, quality=100, dpi=(72, 72))
                    temp_files.append(file_path)
                    
                    print(f"  ✓ Salvo: {os.path.basename(file_path)}")
                    
                    # Progresso
                    if fn is not None:
                        fn(math.ceil(idx * 100) / total_pages)
                    
                except Exception as e:
                    print(f"  ✗ Erro: {e}")
            
            files = temp_files
                    
        except Exception as e:
            print(f"[GeassComics] ✗ Erro: {e}")
        
        print(f"[GeassComics] Download concluído: {len(files)}/{total_pages} imagens")
        return DownloadedChapter(pages.number, files)
