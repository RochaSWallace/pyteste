import json
import re
from time import sleep
from pathlib import Path
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage, ChromiumOptions
from core.__seedwork.infra.http import Http
from core.config.login_data import insert_login, LoginData, get_login
from core.providers.domain.entities import Chapter, Pages, Manga
from core.providers.infra.template.wordpress_etoshore_manga_theme import WordpressEtoshoreMangaTheme


class ArgosComicProvider(WordpressEtoshoreMangaTheme):
    name = 'Argos Comic'
    lang = 'pt_Br'
    domain = ['aniargos.com', 'argoscomic.com']
    has_login = True

    def __init__(self):
        self.url = 'https://aniargos.com'
        self.link = 'https://aniargos.com/'
        self.domain_name = 'aniargos.com'
        self.login_url = self.url
        self._next_action_hash = '6069de63812f052717c7f023fe4ae06fdea27dddf1'
        self._next_get_pages_action_hash = '60bb5c39621f2f5741b7a2e1831b4e19f3628557c7'
        self._project_payload_cache = {}
        self._action_hashes_cache = None

    def _extract_cookies(self, cookies) -> dict:
        cookies_dict = {}

        for cookie in cookies:
            if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                cookies_dict[cookie.name] = cookie.value
            elif isinstance(cookie, dict):
                name = cookie.get('name')
                value = cookie.get('value')
                if name and value:
                    cookies_dict[name] = value

        return cookies_dict

    def _ensure_login_alias_for_domain(self, domain_name: str):
        normalized = (domain_name or '').strip().lower()
        if not normalized:
            return

        if get_login(normalized):
            return

        # Aniargos e ArgosComic compartilham sessão no projeto.
        aliases = ['aniargos.com', 'argoscomic.com', self.domain_name]
        for alias in aliases:
            login_info = get_login(alias)
            if not login_info:
                continue

            headers = getattr(login_info, 'headers', None) or {}
            cookies = getattr(login_info, 'cookies', None) or {}
            if not headers and not cookies:
                continue

            insert_login(LoginData(normalized, headers, cookies))
            return

    def login(self):
        login_info = get_login(self.domain_name) or get_login('argoscomic.com')
        if login_info:
            print(f'[ArgosComic] Login encontrado em cache ({self.domain_name})')
            return True

        print('[ArgosComic] Iniciando navegador para login...')
        print('[ArgosComic] Voce tem 45 segundos para concluir o login manual')

        try:
            co = ChromiumOptions()
            co.headless(False)

            page = ChromiumPage(addr_or_opts=co)
            page.get(self.login_url)
            print(f'[ArgosComic] Aguardando em: {self.login_url}')
            sleep(45)

            cookies_dict = self._extract_cookies(page.cookies())
            if page.states.is_alive:
                page.quit()

            if not cookies_dict:
                print('[ArgosComic] Nenhum cookie foi capturado')
                return False

            insert_login(LoginData(self.domain_name, {}, cookies_dict))
            insert_login(LoginData('argoscomic.com', {}, cookies_dict))
            insert_login(LoginData('aniargos.com', {}, cookies_dict))
            print(f'[ArgosComic] Login salvo com sucesso ({len(cookies_dict)} cookies)')
            return True
        except ImportError:
            print('[ArgosComic] DrissionPage nao esta instalado. Execute: pip install DrissionPage')
            return False
        except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError) as e:
            print(f'[ArgosComic] Erro durante login: {e}')
            return False

    def _extract_project_and_link(self, link: str):
        parsed = urlparse(link)
        parts = [part for part in parsed.path.split('/') if part]
        if len(parts) < 2:
            raise ValueError(f'URL invalida para extrair projeto e obra: {link}')
        return parts[0], parts[1], parsed

    def _build_next_router_state(self, project_id: str, link_id: str) -> str:
        tree = [
            '',
            {
                'children': [
                    ['projectId', project_id, 'd'],
                    {
                        'children': [
                            ['linkId', link_id, 'd'],
                            {'children': ['__PAGE__', {}, None, None]},
                            None,
                            None,
                        ]
                    },
                    None,
                    None,
                ]
            },
            None,
            None,
            True,
        ]
        return quote(json.dumps(tree, separators=(',', ':')), safe='')

    def _parse_x_component_payload(self, raw_content: bytes) -> dict:
        text = raw_content.decode('utf-8', errors='ignore').replace('\ufeff', '')

        if text.strip() == '{}':
            raise ValueError('Resposta vazia do endpoint. Verifique login/cookies.')

        merged_payload = {}
        parsed_blocks = 0
        list_payload = []

        # O x-component pode vir em linhas separadas (0:\n1:) ou tudo em uma linha (0:{...}1:[...]).
        # Capturamos os blocos numerados pela posição e parseamos cada trecho isoladamente.
        block_starts = list(re.finditer(r'(\d+):(?=[\[{\"])', text))

        if not block_starts:
            raise ValueError('Nao foi possivel extrair payload x-component')

        for index, block_match in enumerate(block_starts):
            content_start = block_match.end()
            content_end = block_starts[index + 1].start() if index + 1 < len(block_starts) else len(text)
            content = text[content_start:content_end].strip()
            if not content:
                continue

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                parsed_blocks += 1
                # A resposta x-component pode fragmentar os dados em múltiplas linhas 0:,1:,2:...
                # e o bloco com capítulos pode vir separado do bloco com title.
                merged_payload.update(parsed)

            if isinstance(parsed, list) and parsed:
                list_payload.extend([item for item in parsed if isinstance(item, dict)])

        if parsed_blocks and ('title' in merged_payload or 'Group' in merged_payload or 'groups' in merged_payload):
            return merged_payload

        if list_payload:
            return {'items': list_payload}

        if merged_payload:
            return merged_payload

        raise ValueError('Nao foi possivel extrair payload x-component')

    def _fetch_title_from_html(self, route_url: str) -> str:
        try:
            response = Http.get(route_url, headers={'referer': f'{self.url}/'})
            soup = BeautifulSoup(response.content, 'html.parser')

            og_title = soup.select_one('meta[property="og:title"]')
            if og_title:
                content = (og_title.get('content') or '').strip()
                if content:
                    return content

            if soup.title and soup.title.text:
                title = soup.title.text.strip()
                if title:
                    return title.split('|')[0].strip()
        except (AttributeError, TypeError, ValueError):
            pass

        return ''

    def _chapter_number_sort_key(self, chapter_number: str):
        number_text = str(chapter_number).strip()
        if number_text.replace('.', '', 1).isdigit():
            return (0, float(number_text))
        return (1, number_text)

    def _extract_chapter_numbers_from_text(self, text: str):
        if not text:
            return []

        chapter_numbers = set()
        patterns = [
            r'/capitulo/([0-9]+(?:-[0-9]+)?)',
            r'"chapterId","([0-9]+(?:-[0-9]+)?)"',
        ]

        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                normalized = str(match).replace('-', '.')
                chapter_numbers.add(normalized)

        return sorted(chapter_numbers, key=self._chapter_number_sort_key)

    def _extract_chapter_numbers_from_text_for_project(self, text: str, project_id: str, link_id: str):
        if not text:
            return []

        chapter_numbers = set()
        escaped_project = re.escape(project_id)
        escaped_link = re.escape(link_id)
        scoped_pattern = rf'/{escaped_project}/{escaped_link}/capitulo/([0-9]+(?:-[0-9]+)?)'

        for match in re.findall(scoped_pattern, text, flags=re.IGNORECASE):
            chapter_numbers.add(str(match).replace('-', '.'))

        if not chapter_numbers:
            # fallback mais amplo caso a URL venha sem projeto no href final
            loose_pattern = rf'/{escaped_link}/capitulo/([0-9]+(?:-[0-9]+)?)'
            for match in re.findall(loose_pattern, text, flags=re.IGNORECASE):
                chapter_numbers.add(str(match).replace('-', '.'))

        return sorted(chapter_numbers, key=self._chapter_number_sort_key)

    def _fetch_chapter_numbers_via_get_rsc(self, route_url: str):
        rsc_tokens = ['1r34m', 'gxqs1', '1xkpa']
        request_urls = [route_url] + [f'{route_url}?_rsc={token}' for token in rsc_tokens]

        found_numbers = set()
        for request_url in request_urls:
            headers = {'referer': f'{self.url}/'}
            if '_rsc=' in request_url:
                headers['accept'] = 'text/x-component,*/*;q=0.8'

            try:
                response = Http.get(request_url, headers=headers)
                text = response.content.decode('utf-8', errors='ignore')
            except (AttributeError, TypeError, ValueError):
                continue

            for chapter_number in self._extract_chapter_numbers_from_text(text):
                found_numbers.add(chapter_number)

        return sorted(found_numbers, key=self._chapter_number_sort_key)

    def _fetch_chapter_numbers_via_rendered_dom(self, route_url: str, project_id: str, link_id: str):
        page = None
        try:
            co = ChromiumOptions()
            co.headless(True)

            page = ChromiumPage(addr_or_opts=co)
            page.get(route_url)
            sleep(6)

            try:
                chapters_tab = page.ele('xpath://button[contains(.,"Cap") or contains(.,"chap")]', timeout=4)
                if chapters_tab:
                    chapters_tab.click()
                    sleep(3)
            except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError):
                pass

            html = page.html or ''
            return self._extract_chapter_numbers_from_text_for_project(html, project_id, link_id)
        except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError):
            return []
        finally:
            if page:
                try:
                    page.quit()
                except (AttributeError, RuntimeError, TimeoutError, TypeError, ValueError):
                    pass

    def _coerce_project_payload(self, payload: dict, link_id: str) -> dict:
        items = payload.get('items')
        if not isinstance(items, list):
            return payload

        selected_item = None
        for item in items:
            if isinstance(item, dict) and item.get('link') == link_id:
                selected_item = item
                break

        if selected_item is None:
            selected_item = next((item for item in items if isinstance(item, dict)), None)

        if selected_item is None:
            raise ValueError('Payload em lista sem item valido para manga/capitulos')

        return selected_item

    def _extract_next_action_hash(self, js_content: str, action_name: str) -> str | None:
        escaped_action = re.escape(action_name)
        patterns = [
            rf'createServerReference\)\("([a-f0-9]{{20,}})"[^\n]*"{escaped_action}"',
            rf'createServerReference\("([a-f0-9]{{20,}})"[^\n]*"{escaped_action}"',
            rf'createServerReference\)\(\\"([a-f0-9]{{20,}})\\"[^\n]*\\"{escaped_action}\\"',
        ]

        for pattern in patterns:
            try:
                match = re.search(pattern, js_content)
            except re.error:
                continue
            if match:
                return match.group(1)

        return None

    def _resolve_action_hashes_from_local_chunks(self) -> dict:
        if self._action_hashes_cache is not None:
            return self._action_hashes_cache

        action_hashes = {}
        target_file = '9d756b474caaadb8.js'
        chunk_dir = Path(__file__).parent
        js_files = sorted(
            chunk_dir.glob('*.js'),
            key=lambda p: (0 if p.name == target_file else 1, p.name),
        )

        pattern = re.compile(r'createServerReference\)\("([a-f0-9]{20,})".*?"([A-Za-z0-9_]+)"\)')
        for js_file in js_files:
            try:
                content = js_file.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue

            for match in pattern.finditer(content):
                action_hash = match.group(1)
                action_name = match.group(2)
                if action_name in ('getOne', 'getAllChapters', 'getPages') and action_name not in action_hashes:
                    action_hashes[action_name] = action_hash

            if 'getOne' in action_hashes and 'getAllChapters' in action_hashes and 'getPages' in action_hashes:
                break

        self._action_hashes_cache = action_hashes
        return action_hashes

    def _post_action_payload(self, route_url: str, base_url: str, project_id: str, link_id: str, action_hash: str, body_data: list):
        headers = {
            'accept': 'text/x-component',
            'content-type': 'text/plain;charset=UTF-8',
            'next-action': action_hash,
            'next-router-state-tree': self._build_next_router_state(project_id, link_id),
            'origin': base_url,
            'referer': route_url,
        }

        request_urls = [route_url, f'{route_url}?_rsc=113ik']
        body = json.dumps(body_data, separators=(',', ':'))

        saw_success_2xx = False
        for request_url in request_urls:
            headers['referer'] = request_url
            response = Http.post(request_url, data=body, headers=headers)
            response_status = getattr(response, 'status', None)

            if response_status not in range(200, 300):
                continue

            saw_success_2xx = True

            response_text = response.content.decode('utf-8', errors='ignore')
            if 'Server action not found' in response_text:
                continue

            try:
                return self._parse_x_component_payload(response.content), saw_success_2xx
            except ValueError:
                continue

        return None, saw_success_2xx

    def _resolve_action_hash_from_route(self, route_url: str, base_url: str, action_name: str) -> str | None:
        html_response = Http.get(route_url, headers={'referer': f'{base_url}/'})
        soup = BeautifulSoup(html_response.content, 'html.parser')

        script_urls = []
        for script in soup.select('script[src]'):
            src = (script.get('src') or '').strip()
            if not src or '/_next/static/chunks/' not in src:
                continue
            if src.startswith('//'):
                src = f'https:{src}'
            elif src.startswith('/'):
                src = f'{base_url}{src}'
            if src.startswith('http') and src not in script_urls:
                script_urls.append(src)

        for script_url in script_urls:
            try:
                js_response = Http.get(script_url, headers={'referer': route_url})
                js_text = js_response.content.decode('utf-8', errors='ignore')
                action_hash = self._extract_next_action_hash(js_text, action_name)
                if action_hash:
                    return action_hash
            except (UnicodeDecodeError, ValueError, TypeError):
                continue

        return None

    def _extract_page_urls_from_action_payload(self, payload: dict, project_id: str = ''):
        pages = payload.get('pages') if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            return []

        normalized_pages = []
        for page in pages:
            if isinstance(page, str):
                url = self._normalize_image_url(page)
                order = 0
            elif isinstance(page, dict):
                raw_url = (
                    page.get('photo')
                    or page.get('url')
                    or page.get('src')
                    or page.get('image')
                    or ''
                )
                url = self._normalize_image_url(str(raw_url))
                order = page.get('pageNumber') if isinstance(page.get('pageNumber'), int) else 0
            else:
                continue

            if not url:
                continue

            low = url.lower()
            if project_id and f'/mangas/{project_id.lower()}/' not in low:
                continue
            if '/storage/v1/object/public/argos-comic/mangas/' not in low:
                continue

            normalized_pages.append((order, url))

        normalized_pages.sort(key=lambda item: item[0])

        urls = []
        seen = set()
        for _, url in normalized_pages:
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)

        return urls

    def _fetch_page_urls_via_action(self, chapter_url: str, base_url: str, project_id: str, link_id: str, chapter_slug: str):
        chapter_id = (chapter_slug or '').replace('-', '.')
        if not project_id or not chapter_id:
            return []

        action_hashes = self._resolve_action_hashes_from_local_chunks()
        raw_candidates = [
            action_hashes.get('getPages'),
            self._next_get_pages_action_hash,
            '60bb5c39621f2f5741b7a2e1831b4e19f3628557c7',
        ]

        candidates = []
        seen_candidates = set()
        for action_hash in raw_candidates:
            if not action_hash or action_hash in seen_candidates:
                continue
            seen_candidates.add(action_hash)
            candidates.append(action_hash)

        request_urls = [chapter_url, f'{chapter_url}?_rsc=113ik']
        body_candidates = [[project_id, chapter_id], [project_id, chapter_slug]]

        def try_action_hash(action_hash: str):
            headers = {
                'accept': 'text/x-component',
                'content-type': 'text/plain;charset=UTF-8',
                'next-action': action_hash,
                'next-router-state-tree': self._build_next_router_state(project_id, link_id),
                'origin': base_url,
                'referer': chapter_url,
            }

            for body_data in body_candidates:
                body = json.dumps(body_data, separators=(',', ':'))

                for request_url in request_urls:
                    headers['referer'] = request_url
                    response = Http.post(request_url, data=body, headers=headers)
                    response_status = getattr(response, 'status', None)
                    if response_status not in range(200, 300):
                        continue

                    response_text = response.content.decode('utf-8', errors='ignore')
                    if 'Server action not found' in response_text:
                        continue

                    try:
                        payload = self._parse_x_component_payload(response.content)
                    except ValueError:
                        continue

                    urls = self._extract_page_urls_from_action_payload(payload, project_id)
                    if urls:
                        self._next_get_pages_action_hash = action_hash
                        return urls

            return []

        for action_hash in candidates:
            urls = try_action_hash(action_hash)
            if urls:
                return urls

        route_hash = self._resolve_action_hash_from_route(chapter_url, base_url, 'getPages')
        if route_hash and route_hash not in seen_candidates:
            urls = try_action_hash(route_hash)
            if urls:
                return urls

        return []

    def _fetch_project_payload(self, link: str) -> dict:
        cached = self._project_payload_cache.get(link)
        if cached is not None:
            return cached

        project_id, link_id, parsed = self._extract_project_and_link(link)
        base_url = f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else self.url
        route_url = f'{base_url}/{project_id}/{link_id}'
        self._ensure_login_alias_for_domain(parsed.netloc)

        action_hashes = self._resolve_action_hashes_from_local_chunks()
        raw_get_one_candidates = [
            action_hashes.get('getOne'),
            self._next_action_hash,
            '6069de63812f052717c7f023fe4ae06fdea27dddf1',
            '60cd75a67aff856ebf1ed4c851b5ddee98e381b4ab',
        ]

        get_one_candidates = []
        seen_hashes = set()
        for action_hash in raw_get_one_candidates:
            if not action_hash or action_hash in seen_hashes:
                continue
            seen_hashes.add(action_hash)
            get_one_candidates.append(action_hash)

        payload = None
        for action_hash in get_one_candidates:
            if not action_hash:
                continue

            parsed_payload, saw_success_2xx = self._post_action_payload(
                route_url=route_url,
                base_url=base_url,
                project_id=project_id,
                link_id=link_id,
                action_hash=action_hash,
                body_data=[project_id, link_id],
            )
            if parsed_payload is None:
                # Se a action respondeu 2xx mas sem parse, evita cair em varredura de hashes que gera cascata de 404.
                if saw_success_2xx:
                    break
                continue

            payload = self._coerce_project_payload(parsed_payload, link_id)
            self._next_action_hash = action_hash
            break

        chapters_payload = None
        need_get_all = payload is None
        if payload is not None:
            has_groups = bool(payload.get('Group') or payload.get('groups'))
            has_flat_chapters = bool(payload.get('Chapter') or payload.get('chapters'))
            need_get_all = not has_groups and not has_flat_chapters

        get_all_hash = action_hashes.get('getAllChapters') or '60807c6797dbce9aca34e67d4f2304f40e9b9a2553'
        if need_get_all and get_all_hash:
            for body_data in ([project_id, link_id], [project_id]):
                parsed_all_chapters, _ = self._post_action_payload(
                    route_url=route_url,
                    base_url=base_url,
                    project_id=project_id,
                    link_id=link_id,
                    action_hash=get_all_hash,
                    body_data=body_data,
                )
                if not isinstance(parsed_all_chapters, dict):
                    continue

                try:
                    chapters_payload = self._coerce_project_payload(parsed_all_chapters, link_id)
                except ValueError:
                    chapters_payload = parsed_all_chapters

                if isinstance(chapters_payload, dict):
                    break

        if payload is not None:
            has_groups = bool(payload.get('Group') or payload.get('groups'))
            has_flat_chapters = bool(payload.get('Chapter') or payload.get('chapters'))
            if not has_groups and not has_flat_chapters and chapters_payload is not None:
                if chapters_payload.get('groups'):
                    payload['groups'] = chapters_payload.get('groups')
                if chapters_payload.get('groupName'):
                    payload['groupName'] = chapters_payload.get('groupName')
                if chapters_payload.get('Chapter'):
                    payload['Chapter'] = chapters_payload.get('Chapter')
                if chapters_payload.get('chapters'):
                    payload['chapters'] = chapters_payload.get('chapters')

        if payload is None and chapters_payload is not None:
            payload = {
                'title': chapters_payload.get('title') or self._fetch_title_from_html(route_url) or link_id.replace('-', ' ').strip().title(),
                'groupName': chapters_payload.get('groupName', ''),
                'groups': chapters_payload.get('groups', []),
                'Chapter': chapters_payload.get('Chapter', []),
                'chapters': chapters_payload.get('chapters', []),
            }

        if payload is not None:
            has_groups = bool(payload.get('Group') or payload.get('groups'))
            has_flat_chapters = bool(payload.get('Chapter') or payload.get('chapters'))
            if not has_groups and not has_flat_chapters:
                fallback_numbers = self._fetch_chapter_numbers_via_get_rsc(route_url)
                if not fallback_numbers:
                    fallback_numbers = self._fetch_chapter_numbers_via_rendered_dom(route_url, project_id, link_id)
                if fallback_numbers:
                    payload['_fallback_chapter_numbers'] = fallback_numbers

        if payload is None:
            fallback_numbers = self._fetch_chapter_numbers_via_get_rsc(route_url)
            if not fallback_numbers:
                fallback_numbers = self._fetch_chapter_numbers_via_rendered_dom(route_url, project_id, link_id)
            if fallback_numbers:
                payload = {
                    'title': self._fetch_title_from_html(route_url) or link_id.replace('-', ' ').strip().title(),
                    'groupName': '',
                    'groups': [],
                    'Chapter': [],
                    'chapters': [],
                    '_fallback_chapter_numbers': fallback_numbers,
                }

        if payload is None:
            raise ValueError('Nao foi possivel extrair payload x-component')

        result = {
            'payload': payload,
            'project_id': project_id,
            'link_id': link_id,
            'base_url': base_url,
        }

        self._project_payload_cache[link] = result
        return result

    def _chapter_sort_key(self, chapter: Chapter):
        number_text = str(chapter.number).strip()
        if number_text.replace('.', '', 1).isdigit():
            return (0, float(number_text))
        return (1, number_text)

    def _normalize_image_url(self, src: str) -> str:
        src = (src or '').strip()
        if not src:
            return ''
        if src.startswith('//'):
            src = f'https:{src}'
        elif src.startswith('/'):
            src = f'{self.url}{src}'
        return src

    def _extract_image_urls_from_html(self, html: str, project_id: str = ''):
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        urls = []
        seen = set()

        def should_keep(url: str) -> bool:
            if not url or not url.startswith('http'):
                return False
            low = url.lower()
            if project_id and f'/mangas/{project_id.lower()}/' in low:
                return True
            if '/storage/v1/object/public/argos-comic/mangas/' in low:
                return True
            if re.search(r'\.(?:webp|jpg|jpeg|png|avif)(?:\?|$)', low):
                return True
            return False

        for img in soup.select('img[src], img[data-src], img[data-lazy-src]'):
            src = self._normalize_image_url(
                img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
            )
            if not should_keep(src):
                continue
            if src in seen:
                continue
            seen.add(src)
            urls.append(src)

        if urls:
            return urls

        for src in re.findall(r'https?://[^"\'\s]+\.(?:webp|jpg|jpeg|png|avif)(?:\?[^"\'\s]*)?', html, flags=re.IGNORECASE):
            src = self._normalize_image_url(src)
            if not should_keep(src):
                continue
            if src in seen:
                continue
            seen.add(src)
            urls.append(src)

        return urls

    def getManga(self, link: str) -> Manga:
        request_data = self._fetch_project_payload(link)
        payload = request_data['payload']
        title = payload.get('title', '').strip()

        if not title:
            project_id, link_id, parsed = self._extract_project_and_link(link)
            base_url = f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else self.url
            route_url = f'{base_url}/{project_id}/{link_id}'
            title = self._fetch_title_from_html(route_url) or link_id.replace('-', ' ').strip().title()

        return Manga(link, title)

    def getChapters(self, link: str):
        request_data = self._fetch_project_payload(link)
        payload = request_data['payload']
        project_id = request_data['project_id']
        link_id = request_data['link_id']
        base_url = request_data['base_url']

        title = payload.get('title', '').strip() or link_id.replace('-', ' ').strip().title()
        groups = payload.get('Group') or payload.get('groups') or []
        flat_chapters = payload.get('Chapter') or payload.get('chapters') or []

        chapters = []
        for group in groups:
            group_chapters = group.get('Chapter') or group.get('chapters') or []
            for chapter_data in group_chapters:
                chapter_title = chapter_data.get('title')
                if chapter_title is None:
                    continue

                chapter_number = str(chapter_title)
                chapter_slug = chapter_number.replace('.', '-')
                chapter_url = f'{base_url}/{project_id}/{link_id}/capitulo/{chapter_slug}'
                chapters.append(Chapter(chapter_url, chapter_number, title))

        for chapter_data in flat_chapters:
            if not isinstance(chapter_data, dict):
                continue

            chapter_title = chapter_data.get('title')
            if chapter_title is None:
                continue

            chapter_number = str(chapter_title)
            chapter_slug = chapter_number.replace('.', '-')
            chapter_url = f'{base_url}/{project_id}/{link_id}/capitulo/{chapter_slug}'
            chapters.append(Chapter(chapter_url, chapter_number, title))

        if not chapters:
            fallback_numbers = payload.get('_fallback_chapter_numbers') or []
            if not fallback_numbers:
                route_url = f'{base_url}/{project_id}/{link_id}'
                fallback_numbers = self._fetch_chapter_numbers_via_get_rsc(route_url)
                if not fallback_numbers:
                    fallback_numbers = self._fetch_chapter_numbers_via_rendered_dom(route_url, project_id, link_id)

            for chapter_number in fallback_numbers:
                chapter_slug = str(chapter_number).replace('.', '-')
                chapter_url = f'{base_url}/{project_id}/{link_id}/capitulo/{chapter_slug}'
                chapters.append(Chapter(chapter_url, str(chapter_number), title))

        if not chapters:
            raise ValueError('Nenhum capitulo encontrado no payload')

        chapters.sort(key=self._chapter_sort_key)
        return chapters

    def getPages(self, ch: Chapter) -> Pages:
        parsed = urlparse(ch.id)
        self._ensure_login_alias_for_domain(parsed.netloc)

        path_parts = [part for part in parsed.path.split('/') if part]
        project_id = path_parts[0] if len(path_parts) >= 1 else ''
        link_id = path_parts[1] if len(path_parts) >= 2 else ''
        chapter_slug = path_parts[3] if len(path_parts) >= 4 else str(ch.number).replace('.', '-')

        base_url = f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else self.url

        urls = self._fetch_page_urls_via_action(
            chapter_url=ch.id,
            base_url=base_url,
            project_id=project_id,
            link_id=link_id,
            chapter_slug=chapter_slug,
        )

        if not urls:
            response = Http.get(ch.id, headers={'referer': f'{self.url}/'})
            html_text = response.content.decode('utf-8', errors='ignore')
            urls = self._extract_image_urls_from_html(html_text, project_id)

        if project_id:
            urls = [url for url in urls if f'/mangas/{project_id.lower()}/' in url.lower()]

        if not urls:
            raise ValueError(f'Nao foi possivel extrair paginas do capitulo: {ch.id}')

        return Pages(ch.id, ch.number, ch.name, urls)
