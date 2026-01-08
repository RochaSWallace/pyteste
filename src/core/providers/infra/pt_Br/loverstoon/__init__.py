from core.providers.infra.template.wordpress_madara import WordPressMadara
from core.__seedwork.infra.http.contract.http import Response
from core.providers.domain.entities import Chapter, Pages, Manga
from bs4 import BeautifulSoup
import re
from core.__seedwork.infra.http import Http
from urllib.parse import urljoin

class LoversToonProvider(WordPressMadara):
    name = 'Lovers toon'
    lang = 'pt-Br'
    domain = ['loverstoon.com']

    def __init__(self):
        self.url = 'https://loverstoon.com'
        self.path = ''
        
        self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
        self.query_chapters = 'li.wp-manga-chapter > a'
        self.query_chapters_title_bloat = None
        self.query_pages = 'img'
        self.query_title_for_uri = 'h1'
        self.query_placeholder = '[id^="manga-chapters-holder"][data-id]'

    def _converter_tempo_para_segundos(self, tempo_texto: str) -> int:
        """
        Converte tempo relativo para segundos
        Formatos: '11 horas ago', '13 horas ago', '1 dia ago', etc.
        """
        tempo_texto = tempo_texto.strip().lower()
        
        # Remove " ago" se existir
        tempo_texto = tempo_texto.replace(' ago', '').replace('ago', '').strip()
        
        # Extrai o número
        match = re.search(r'(\d+)', tempo_texto)
        if not match:
            return 86400  # Padrão 24h se não conseguir parsear
        
        valor = int(match.group(1))
        
        # Identifica a unidade de tempo
        if 'minuto' in tempo_texto or 'min' in tempo_texto:
            return valor * 60
        elif 'hora' in tempo_texto or 'hour' in tempo_texto:
            return valor * 3600
        elif 'dia' in tempo_texto or 'day' in tempo_texto:
            return valor * 86400
        elif 'semana' in tempo_texto or 'week' in tempo_texto or 'sem' in tempo_texto:
            return valor * 604800
        elif 'mês' in tempo_texto or 'mes' in tempo_texto or 'month' in tempo_texto:
            return valor * 2592000
        elif 'segundo' in tempo_texto or 'sec' in tempo_texto:
            return valor
        
        return 86400  # Padrão 24h

    def _converter_data_para_segundos(self, data_texto: str) -> int:
        """
        Converte data no formato DD.MM.YYYY para segundos desde o lançamento
        Exemplo: '22.10.2025', '23.10.2025'
        """
        from datetime import datetime
        
        try:
            # Parse formato "DD.MM.YYYY"
            data_lancamento = datetime.strptime(data_texto.strip(), '%d.%m.%Y')
            
            # Calcula diferença
            diferenca = datetime.now() - data_lancamento
            return int(diferenca.total_seconds())
            
        except Exception as e:
            print(f"[LoversToon] Erro ao converter data '{data_texto}': {e}")
            return 86400 * 7  # Padrão 7 dias

    def getPages(self, ch: Chapter) -> Pages:
        """
        Extrai as URLs das imagens diretamente do script JavaScript no HTML.
        As imagens estão em um array JSON dentro de um fetch para a API cache.
        """
        uri = urljoin(self.url, ch.id)
        response = Http.get(uri, timeout=getattr(self, 'timeout', None))
        soup = BeautifulSoup(response.content, 'html.parser')
        
        list = []
        
        # Procura pelo script que contém o array de imagens
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            
            # Procura pelo padrão: content: ["url1","url2",...]
            match = re.search(r'content:\s*\[(.*?)\]', script_text, re.DOTALL)
            if match:
                # Extrai o conteúdo do array
                array_content = match.group(1)
                
                # Extrai todas as URLs (entre aspas)
                urls = re.findall(r'"(https?://[^"]+)"', array_content)
                
                if urls:
                    list = urls
                    print(f"✅ Encontradas {len(urls)} imagens no script JavaScript")
                    for url in urls:
                        print(url)
                    break
        
        # Validar se encontrou páginas
        if not list:
            raise Exception(f"❌ Nenhuma imagem encontrada no HTML. Verifique se o padrão do script mudou.")

        # Extrair número com segurança
        matches = re.findall(r'\d+\.?\d*', str(ch.number))
        number = matches[0] if matches else "0"
        
        return Pages(ch.id, number, ch.name, list)