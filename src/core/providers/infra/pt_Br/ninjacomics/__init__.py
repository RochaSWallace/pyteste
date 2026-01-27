import re
import json
from time import sleep
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage, ChromiumOptions
from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.config.login_data import insert_login, LoginData, get_login, delete_login

class NinjaComicsProvider(WordPressMadara):
    name = 'Ninja Comics'
    lang = 'pt_Br'
    domain = ['ninjacomics.xyz']
    has_login = True

    def __init__(self):
        self.url = 'https://ninjacomics.xyz'
        self.domain_name = 'ninjacomics.xyz'
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'div.page-break.no-gaps'
        self.query_title_for_uri = 'head meta[property="og:title"]'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'
    
    def _is_logged_in(self, html) -> bool:
        """Verifica se está logado analisando o HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Procura por indicadores de login
        user_menu = soup.select_one('.c-user_menu, .user-menu, .logged-in')
        login_link = soup.select_one('a[href*="login"], a.login')
        
        # Se não tem link de login, está logado
        if not login_link and user_menu:
            return True
        
        # Se tem link de login, não está logado
        if login_link:
            return False
            
        return False
    
    def login(self):
        """Realiza login usando DrissionPage para capturar cookies do navegador real"""
        login_info = get_login(self.domain_name)
        if login_info:
            print("[NinjaComics] ✅ Login encontrado em cache")
            return True
        
        print("[NinjaComics] 🔐 Iniciando navegador para login...")
        print("[NinjaComics] 📝 Você tem 30 segundos para fazer login")
        
        try:
            # Configurar opções do navegador
            co = ChromiumOptions()
            co.headless(False)
            
            # Criar página
            page = ChromiumPage(addr_or_opts=co)
            page.get(f'{self.url}/home-dark/')
            
            print("[NinjaComics] ⏳ Aguardando 30 segundos...")
            sleep(30)
            
            print("[NinjaComics] ✅ Capturando cookies...")
            
            # Captura todos os cookies
            cookies = page.cookies()
            cookies_dict = {}
            
            # DrissionPage retorna um objeto CookiesList, não um dict
            for cookie in cookies:
                if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                    cookies_dict[cookie.name] = cookie.value
                elif isinstance(cookie, dict):
                    cookies_dict[cookie.get('name')] = cookie.get('value')
            
            print(f"[NinjaComics] 🍪 {len(cookies_dict)} cookies capturados")
            
            # Fecha o navegador
            page.quit()
            
            # Salva no banco de dados
            if cookies_dict:
                insert_login(LoginData(self.domain_name, {}, cookies_dict))
                print("[NinjaComics] ✅ Login salvo com sucesso!")
                return True
            else:
                print("[NinjaComics] ❌ Nenhum cookie capturado")
                return False
                
        except ImportError:
            print("[NinjaComics] ❌ DrissionPage não está instalado")
            print("[NinjaComics] Execute: pip install DrissionPage")
            return False
        except Exception as e:
            print(f"[NinjaComics] ❌ Erro durante login: {e}")
            return False