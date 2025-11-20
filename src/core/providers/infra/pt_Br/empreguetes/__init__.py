import re
import math
import asyncio
import nodriver as uc
from typing import List
from bs4 import BeautifulSoup
from core.__seedwork.infra.http import Http
from core.providers.infra.template.base import Base
from core.providers.domain.entities import Chapter, Pages, Manga
import json
import requests

class EmpreguetesProvider(Base):
    name = 'Empreguetes'
    lang = 'pt_Br'
    domain = ['empreguetes.xyz']

    def __init__(self) -> None:
        self.base = 'https://api2.sussytoons.wtf'
        self.CDN = 'https://cdn.sussytoons.wtf'
        self.old = 'https://oldi.sussytoons.site/wp-content/uploads/WP-manga/data/'
        self.oldCDN = 'https://oldi.sussytoons.site/scans/1/obras'
        self.chapter = 'https://empreguetes.xyz/capitulo'
        self.webBase = 'https://empreguetes.xyz'
        self.cookies = [{'sussytoons-terms-accepted', 'true'}]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': 'https://empreguetes.xyz',
            'Referer': 'https://empreguetes.xyz/',
            'scan-id': 'empreguetes.xyz'
        }
    
    def getManga(self, link: str) -> Manga:
        match = re.search(r'/obra/([^/?]+)', link)
        if not match:
            raise Exception("Slug da obra não encontrado na URL")
            
        slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
        api_url = f'{self.base}/obras/{slug}'
        response = requests.get(api_url, headers={'scan-id': 'empreguetes.xyz'})
        data = response.json()
        title = data.get('obr_nome', 'Título Desconhecido')
        return Manga(link, title)

    def getChapters(self, id: str) -> List[Chapter]:
        try:
            match = re.search(r'/obra/([^/?]+)', id)
            if not match:
                raise Exception("Slug da obra não encontrado")
                
            slug = match.group(1)
            
            # Nova API usa slug ao invés de ID
            api_url = f'{self.base}/obras/{slug}'
            response = requests.get(api_url, headers={'scan-id': 'empreguetes.xyz'})
            data = response.json()
            
            title = data.get('obr_nome', 'Título Desconhecido')
            chapters_list = []
            for ch in data.get('capitulos', []):
                # Agora armazena [slug, cap_id] para manter compatibilidade
                chapters_list.append(Chapter([slug, ch['cap_id']], ch['cap_nome'], title))
            return chapters_list
        except Exception as e:
            print(f"[SussyToons] Erro em getChapters: {e}")
            return []

    def get_Pages(self, id, sleep, background=False):
        async def get_Pages_driver():
            inject_script = """
            const mockResponse = {
                statusCode: 200,
                resultado: {
                    usr_id: 83889,
                    usr_nome: "White_Preto",
                    usr_email: "emailgay@gmail.com",
                    usr_nick: "emailgay",
                    usr_imagem: null,
                    usr_banner: null,
                    usr_moldura: null,
                    usr_criado_em: "2025-02-26 16:34:19.591",
                    usr_atualizado_em: "2025-02-26 16:34:19.591",
                    usr_status: "ATIVO",
                    vip_habilitado: true,
                    vip_habilitado_em: "2025-02-26 16:34:19.591",
                    vip_temporario_em: null,
                    vip_acaba_em: "2035-02-26 16:34:19.591",
                    usr_google_token: null,
                    scan: {
                        scan_id: 3,
                        scan_nome: "Empreguetes"
                    },
                    scan_id: 3,
                    tags: []
                }
            };

            // Intercepta todas as requisições para a API
            const originalFetch = window.fetch;
            window.fetch = async function(url, options) {
                if (url.includes('api.sussytoons.wtf/me')) {
                    return new Response(JSON.stringify(mockResponse), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'}
                    });
                }
                return originalFetch(url, options);
            };
            """

            browser = await uc.start(
                browser_args=[
                    '--window-size=600,600', 
                    f'--app={id}',
                    '--disable-extensions', 
                    '--disable-popup-blocking'
                ],
                browser_executable_path=None,
                headless=background
            )
            page = await browser.get(id)
            await browser.cookies.set_all(self.cookies)
            
            await page.evaluate(inject_script)
            
            await asyncio.sleep(sleep)
            html = await page.get_content()
            browser.stop() 
            return html
        resultado = uc.loop().run_until_complete(get_Pages_driver())
        return resultado
    
    def getPages(self, ch: Chapter) -> Pages:
        images = []
        
        try:
            # Usar API com requests
            api_url = f"{self.base}/capitulos/{ch.id[1]}"
            print(f"[SussyToons] Chamando API: {api_url}")
            
            headers_with_scan_id = {**self.headers, 'scan-id': 'empreguetes.xyz'}
            response = requests.get(f"{self.base}/capitulos/{ch.id[1]}", headers=headers_with_scan_id, timeout=30)
            # JSON já vem direto, sem 'resultado'
            data = response.json()
            print(data)
            obra_id = data.get('obr_id', 'Desconhecido')
            cap_numero = data.get('cap_numero', 'Desconhecido')

            def clean_path(p):
                return p.strip('/') if p else ''

            for i, pagina in enumerate(data.get('cap_paginas', [])):
                try:
                    mime = pagina.get('mime')
                    path = clean_path(pagina.get('path', 'false'))
                    src = clean_path(pagina.get('src', ''))
                    
                    if mime is not None:
                        # Novo formato CDN
                        full_url = f"https://cdn.sussytoons.site/wp-content/uploads/WP-manga/data/{src}"
                        print(1)
                    elif path == 'false' or path == '' or path is None or path.lower() == 'none':
                        full_url = f"https://cdn.sussytoons.wtf/scans/3/obras/{obra_id}/capitulos/{cap_numero}/{src}"
                        print(2)
                    else:
                        # Formato antigo
                        if 'jpg' in path.lower() or 'png' in path.lower() or 'jpeg' in path.lower() or 'webp' in path.lower():
                           full_url = f"{self.CDN}/{path}"
                        else:
                            full_url = f"{self.CDN}/{path}/{src}"
                    
                    if full_url and full_url.startswith('http'):
                        if ' ' in full_url:
                            full_url = full_url.replace(' ', '%20')
                        images.append(full_url)
                        print(f"[Empreguetes] Página {i+1}: {full_url}")
                    
                except Exception as e:
                    continue
            
            if images:
                return Pages(ch.id, ch.number, ch.name, images)
            else:
                print("[Empreguetes] ⚠️ Nenhuma página válida encontrada")
                
        except Exception as e:
            print(f"[Empreguetes] ❌ Erro na API: {e}")

        # Se chegou aqui, API falhou - retornar páginas vazias
        print("[Empreguetes] ❌ Falha na API - retornando lista vazia")
        return Pages(ch.id, ch.number, ch.name, [])