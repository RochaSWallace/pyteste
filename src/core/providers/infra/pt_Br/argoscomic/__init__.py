from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme
from typing import List
from bs4 import BeautifulSoup
import time
import threading
import atexit
import undetected_chromedriver as uc
from core.providers.domain.entities import Chapter, Pages, Manga
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Pool global de navegadores para evitar sobrecarga
_DRIVER_POOL = []
_DRIVER_LOCK = threading.Lock()
_MAX_DRIVERS = 10  # Máximo de navegadores simultâneos
_DRIVER_LAST_USED = {}  # Rastreia quando cada driver foi usado pela última vez
_IDLE_TIMEOUT = 20  # 20 segundos de timeout para drivers inativos
_CLEANUP_THREAD = None
_CLEANUP_RUNNING = False

def _cleanup_all_drivers():
    """Fecha todos os navegadores do pool - chamado ao encerrar o programa"""
    global _DRIVER_POOL, _DRIVER_LOCK, _DRIVER_LAST_USED, _CLEANUP_RUNNING
    
    print("[DEBUG] Fechando todos os navegadores do pool...")
    
    # Para o thread de limpeza
    _CLEANUP_RUNNING = False
    
    with _DRIVER_LOCK:
        for driver in _DRIVER_POOL:
            try:
                driver.quit()
                print("[DEBUG] Navegador fechado com sucesso")
            except Exception as e:
                print(f"[DEBUG] Erro ao fechar navegador: {e}")
        _DRIVER_POOL.clear()
        _DRIVER_LAST_USED.clear()
    print("[DEBUG] Todos os navegadores foram fechados")

def _cleanup_idle_drivers():
    """Remove navegadores que ficaram inativos por muito tempo"""
    global _DRIVER_POOL, _DRIVER_LOCK, _DRIVER_LAST_USED, _IDLE_TIMEOUT
    
    current_time = time.time()
    with _DRIVER_LOCK:
        drivers_to_remove = []
        
        for i, driver in enumerate(_DRIVER_POOL):
            driver_id = id(driver)
            last_used = _DRIVER_LAST_USED.get(driver_id, current_time)
            
            # Se o driver está inativo por mais tempo que o timeout
            if current_time - last_used > _IDLE_TIMEOUT:
                try:
                    driver.quit()
                    drivers_to_remove.append(i)
                    print(f"[DEBUG] Navegador inativo fechado (inativo por {current_time - last_used:.0f}s)")
                except Exception as e:
                    print(f"[DEBUG] Erro ao fechar navegador inativo: {e}")
                    drivers_to_remove.append(i)
        
        # Remove os drivers fechados do pool (em ordem reversa para não afetar os índices)
        for i in reversed(drivers_to_remove):
            driver_id = id(_DRIVER_POOL[i])
            _DRIVER_POOL.pop(i)
            _DRIVER_LAST_USED.pop(driver_id, None)

def _background_cleanup_worker():
    """Worker thread que roda em background limpando drivers inativos"""
    global _CLEANUP_RUNNING, _IDLE_TIMEOUT
    
    print("[DEBUG] Thread de limpeza automática iniciada")
    
    while _CLEANUP_RUNNING:
        try:
            time.sleep(_IDLE_TIMEOUT / 2)  # Verifica a cada metade do timeout
            if _CLEANUP_RUNNING:  # Verifica novamente após o sleep
                _cleanup_idle_drivers()
        except Exception as e:
            print(f"[DEBUG] Erro no thread de limpeza: {e}")
    
    print("[DEBUG] Thread de limpeza automática finalizada")

def _start_cleanup_thread():
    """Inicia o thread de limpeza automática se não estiver rodando"""
    global _CLEANUP_THREAD, _CLEANUP_RUNNING
    
    if _CLEANUP_THREAD is None or not _CLEANUP_THREAD.is_alive():
        _CLEANUP_RUNNING = True
        _CLEANUP_THREAD = threading.Thread(target=_background_cleanup_worker, daemon=True)
        _CLEANUP_THREAD.start()
        print("[DEBUG] Thread de limpeza automática iniciada")

# Registra a função de limpeza para ser executada ao sair do programa
atexit.register(_cleanup_all_drivers)

class ArgosComicProvider(WordpressEtoshoreMangaTheme):
    name = 'Argos Comic'
    lang = 'pt_Br'
    domain = ['argoscomic.com']

    def __init__(self):
        self.url = 'https://argoscomic.com'
        self.link = 'https://argoscomic.com/'

        self.get_title = 'h1.text-2xl'
        self.get_chapters_list = 'div.space-y-6'
        self.chapter = 'a'
        self.get_chapter_number = 'span.font-medium'
        self.get_div_page = 'div.flex.flex-col.items-center'
        self.get_pages = 'img'

    def _get_driver_from_pool(self):
        """Obtém um navegador do pool ou cria um novo se necessário"""
        global _DRIVER_POOL, _DRIVER_LOCK, _MAX_DRIVERS, _DRIVER_LAST_USED
        
        # Inicia o thread de limpeza automática se não estiver rodando
        _start_cleanup_thread()
        
        # Limpa drivers inativos manualmente também (dupla verificação)
        _cleanup_idle_drivers()
        
        with _DRIVER_LOCK:
            # Tenta reutilizar um navegador existente
            for i, driver in enumerate(_DRIVER_POOL):
                try:
                    # Testa se o navegador ainda está funcional
                    _ = driver.current_url
                    # Remove do pool temporariamente para uso exclusivo
                    driver_obj = _DRIVER_POOL.pop(i)
                    # Atualiza o timestamp de uso
                    _DRIVER_LAST_USED[id(driver_obj)] = time.time()
                    return driver_obj
                except:
                    # Navegador não funcional, remove da pool
                    try:
                        driver.quit()
                    except:
                        pass
                    _DRIVER_POOL.pop(i)
                    _DRIVER_LAST_USED.pop(id(driver), None)
                    break
            
            # Se não há navegadores disponíveis e não excedeu o limite, cria um novo
            if len(_DRIVER_POOL) < _MAX_DRIVERS:
                try:
                    options = uc.ChromeOptions()
                    options.add_argument('--headless')
                    options.add_argument('--no-sandbox')
                    options.add_argument('--disable-gpu')
                    options.add_argument('--disable-dev-shm-usage')
                    prefs = {"profile.managed_default_content_settings.images": 2}
                    options.add_experimental_option("prefs", prefs)
                    
                    new_driver = uc.Chrome(options=options)
                    # Registra o timestamp de criação
                    _DRIVER_LAST_USED[id(new_driver)] = time.time()
                    print(f"[DEBUG] Criando nova instância do Chrome (pool size: {len(_DRIVER_POOL) + 1})")
                    return new_driver
                except Exception as e:
                    print(f"[DEBUG] Erro ao criar navegador: {e}")
                    return None
            
            # Se o pool está cheio, aguarda um pouco e tenta novamente
            print("[DEBUG] Pool de navegadores cheio, aguardando...")
            return None

    def _return_driver_to_pool(self, driver):
        """Retorna um navegador para o pool"""
        global _DRIVER_POOL, _DRIVER_LOCK, _MAX_DRIVERS, _DRIVER_LAST_USED
        
        if not driver:
            return
            
        with _DRIVER_LOCK:
            try:
                # Verifica se o navegador ainda está funcional
                _ = driver.current_url
                
                # Atualiza o timestamp de último uso
                _DRIVER_LAST_USED[id(driver)] = time.time()
                
                # Se o pool não estiver cheio, adiciona de volta
                if len(_DRIVER_POOL) < _MAX_DRIVERS:
                    _DRIVER_POOL.append(driver)
                    print(f"[DEBUG] Navegador retornado ao pool (pool size: {len(_DRIVER_POOL)})")
                else:
                    # Pool cheio, fecha o navegador
                    driver.quit()
                    _DRIVER_LAST_USED.pop(id(driver), None)
                    print("[DEBUG] Pool cheio, navegador fechado")
            except:
                # Navegador não funcional, tenta fechar
                try:
                    driver.quit()
                except:
                    pass
                _DRIVER_LAST_USED.pop(id(driver), None)

    def _get_driver_with_retry(self, max_retries=10):
        """Obtém um navegador com retry em caso de pool cheio"""
        for attempt in range(max_retries):
            driver = self._get_driver_from_pool()
            if driver:
                return driver
            
            print(f"[DEBUG] Tentativa {attempt + 1} de obter navegador...")
            time.sleep(1)  # Aguarda 1 segundo antes de tentar novamente
        
        # Se não conseguiu depois de todas as tentativas, cria um novo forçadamente
        print("[DEBUG] Criando navegador emergencial...")
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-dev-shm-usage')
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)
            return uc.Chrome(options=options)
        except Exception as e:
            print(f"[DEBUG] Erro ao criar navegador emergencial: {e}")
            raise e
    
    def getManga(self, link: str) -> Manga:
        driver = None
        try:
            driver = self._get_driver_with_retry()
            driver.get(link)
            time.sleep(1)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.select_one(self.get_title)
            print(title)
            return Manga(link, title.get_text().strip())
        finally:
            if driver:
                self._return_driver_to_pool(driver)


    def getChapters(self, id: str) -> List[Chapter]:
        driver = None
        try:
            driver = self._get_driver_with_retry()
            driver.get(id)
            
            try:
                wait = WebDriverWait(driver, 5)
                load_more_button = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Carregar mais capítulos')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
                
                driver.execute_script("arguments[0].click();", load_more_button)

            except TimeoutException:
                print("Botão 'Carregar mais capítulos' não encontrado. Extraindo capítulos já visíveis. 👍")

            time.sleep(3)
            volumes = driver.find_elements(By.XPATH, "//h2[contains(text(), 'Volume') or contains(text(), 'Temporada') or contains(text(), 'Season') or contains(text(), 'Arco') or contains(text(), 'Parte')]/ancestor::div[contains(@class, 'cursor-pointer')]")
            if volumes:
                for vol in volumes:
                    try:
                        svg = vol.find_element(By.TAG_NAME, "svg")
                        path = svg.find_element(By.TAG_NAME, "path")
                        d = path.get_attribute("d")
                        if d and d.strip().startswith("M17.919"):
                            print(f"Volume fechado encontrado, expandindo...")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", vol)
                            driver.execute_script("arguments[0].click();", vol)
                    except Exception as e:
                        print(f"Erro ao tentar expandir volume: {e}")
                
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            chapters_list = soup.select_one(self.get_chapters_list)
            chapter = chapters_list.select(self.chapter)
            title = soup.select_one(self.get_title)
            list = []
            for ch in chapter:
                number = ch.select_one(self.get_chapter_number)
                list.append(Chapter(f"{self.url}{ch.get('href')}", number.get_text().strip(), title.get_text().strip()))
            
            return list

        finally:
            if driver:
                self._return_driver_to_pool(driver)

    def getPages(self, ch: Chapter) -> Pages:
        print(ch.id)
        driver = None
        try:
            driver = self._get_driver_with_retry()
            driver.get(ch.id)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            scroll_script = '''
            var elements = document.querySelectorAll('*');
            for (var i = 0; i < elements.length; i++) {
                var el = elements[i];
                var style = window.getComputedStyle(el);
                if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                    el.scrollTop = el.scrollHeight;
                }
            }
            '''
            driver.execute_script(scroll_script)
            time.sleep(1)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            img_urls = []
            img_tags = soup.find_all(self.get_pages)
            for img in img_tags:
                src = img.get('src')
                if src:
                    img_urls.append(src)
            
            return Pages(ch.id, ch.number, ch.name, img_urls)
            
        finally:
            if driver:
                self._return_driver_to_pool(driver)
    
    def _open_driver(self, url):
        """Método legado mantido para compatibilidade - agora usa o pool"""
        return self._get_driver_with_retry()

    @staticmethod
    def close_all_drivers():
        """Fecha todos os navegadores do pool - pode ser chamado manualmente"""
        _cleanup_all_drivers()

    @staticmethod
    def get_pool_status():
        """Retorna o status atual do pool de navegadores"""
        global _DRIVER_POOL, _DRIVER_LOCK, _DRIVER_LAST_USED, _IDLE_TIMEOUT, _CLEANUP_RUNNING, _CLEANUP_THREAD
        
        with _DRIVER_LOCK:
            current_time = time.time()
            active_drivers = 0
            idle_drivers = 0
            
            for driver in _DRIVER_POOL:
                try:
                    _ = driver.current_url
                    driver_id = id(driver)
                    last_used = _DRIVER_LAST_USED.get(driver_id, current_time)
                    
                    if current_time - last_used > _IDLE_TIMEOUT:
                        idle_drivers += 1
                    else:
                        active_drivers += 1
                except:
                    pass
            
            cleanup_thread_status = "Rodando" if _CLEANUP_RUNNING and _CLEANUP_THREAD and _CLEANUP_THREAD.is_alive() else "Parado"
            
            return {
                "total_drivers": len(_DRIVER_POOL),
                "active_drivers": active_drivers,
                "idle_drivers": idle_drivers,
                "max_drivers": _MAX_DRIVERS,
                "idle_timeout": _IDLE_TIMEOUT,
                "cleanup_thread_status": cleanup_thread_status
            }

    @staticmethod
    def start_auto_cleanup():
        """Inicia o sistema de limpeza automática manualmente"""
        _start_cleanup_thread()
        print("[DEBUG] Sistema de limpeza automática iniciado manualmente")

    @staticmethod
    def stop_auto_cleanup():
        """Para o sistema de limpeza automática"""
        global _CLEANUP_RUNNING
        _CLEANUP_RUNNING = False
        print("[DEBUG] Sistema de limpeza automática parado manualmente")

    @staticmethod
    def set_idle_timeout(seconds):
        """Define o timeout para drivers inativos"""
        global _IDLE_TIMEOUT
        _IDLE_TIMEOUT = max(10, seconds)  # Mínimo de 10 segundos
        print(f"[DEBUG] Timeout de inatividade definido para {_IDLE_TIMEOUT} segundos")

    def __del__(self):
        """Cleanup quando a instância da classe é destruída"""
        # Não fecha todos os drivers aqui pois podem estar sendo usados por outras instâncias
        pass
