import tldextract
import cloudscraper
from time import sleep
from core.config.login_data import get_login
from core.__seedwork.infra.http.contract.http import Http, Response
from core.config.request_data import get_request, delete_request, insert_request, RequestData
from core.cloudflare.application.use_cases import (
    IsCloudflareBlockingUseCase, 
    BypassCloudflareUseCase, 
    BypassCloudflareNoCapchaUseCase, 
    BypassCloudflareNoCapchaFeachUseCase, 
    IsCloudflareBlockingTimeOutUseCase, 
    IsCloudflareEnableCookies,
    IsCloudflareBlockingBadGateway,
    BypassCloudflareNoCapchaPostUseCase,
    IsCloudflareAttention
)

class HttpService(Http):
    
    @staticmethod
    def get(url: str, params=None, headers=None, cookies=None, timeout=None, **kwargs) -> Response:
        status = 0
        count = 0
        extract = tldextract.extract(url)
        domain = f"{extract.domain}.{extract.suffix}"

        scraper = cloudscraper.create_scraper(    
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }    
        )
     
        while(status not in range(200, 299) and count <= 10):
            count += 1

            request_data = get_request(domain)

            if request_data:
                re = request_data
                if headers is not None:
                    headers = {**headers, **re.headers}
                else:
                    headers = re.headers
                if cookies is not None:
                    cookies = {**cookies, **re.cookies}
                else:
                    cookies = re.cookies
            
            login_data = get_login(domain)

            if login_data:
                re = login_data
                if headers is not None:
                    headers = {**headers, **re.headers}
                else:
                    headers = re.headers
                if cookies is not None:
                    cookies = {**cookies, **re.cookies}
                else:
                    cookies = re.cookies

            response = scraper.get(url, params=params, headers=headers, cookies=cookies, timeout=timeout, **kwargs)
            status = response.status_code

            if response.status_code == 403:
                print(f"<stroke style='color:#add8e6;'>[REQUEST]:</stroke> <span style='color:#add8e6;'>GET</span> <span style='color:red;'>{status}</span> <a href='#'>{url}</a>")
                print(f"[DEBUG] ========== INÍCIO BYPASS CLOUDFLARE (403) ==========")
                print(f"[DEBUG] URL: {url}")
                print(f"[DEBUG] Domain: {domain}")
                
                if IsCloudflareBlockingUseCase().execute(response.text):
                        print(f"[DEBUG] ✓ IsCloudflareBlockingUseCase DETECTOU bloqueio")
                        request_data = get_request(domain)
                        if(request_data):
                            delete_request(domain)
                            print(f"[DEBUG] Cookie antigo deletado")
                        
                        print(f"[DEBUG] → Chamando BypassCloudflareUseCase.execute()")
                        data = BypassCloudflareUseCase().execute(f'https://{domain}')
                        
                        if(data.cloudflare_cookie_value):
                            print(f"[DEBUG] ✓ Cookie cf_clearance obtido via BypassCloudflareUseCase")
                            insert_request(RequestData(domain=domain, headers=data.user_agent, cookies=data.cloudflare_cookie_value))
                            print(f"[DEBUG] Cookie salvo, voltando ao loop para nova tentativa")
                        else:
                            print(f"[DEBUG] ✗ Nenhum cookie obtido, tentando BypassCloudflareNoCapchaUseCase")
                            print(f"[DEBUG] → Chamando BypassCloudflareNoCapchaUseCase.execute()")
                            content = BypassCloudflareNoCapchaUseCase().execute(url)
                            if content and not IsCloudflareBlockingBadGateway().execute(content):
                                print(f"[DEBUG] ✓ Conteúdo obtido via BypassCloudflareNoCapchaUseCase - Retornando Response")
                                return Response(200, 'a', content, url)
                            else:
                                print(f"[DEBUG] ✗ BypassCloudflareNoCapchaUseCase falhou ou retornou Bad Gateway")
                                
                elif IsCloudflareEnableCookies().execute(response.text):
                    print(f"[DEBUG] ✓ IsCloudflareEnableCookies DETECTOU problema de cookies")
                    print(f"[DEBUG] → Chamando BypassCloudflareNoCapchaFeachUseCase.execute()")
                    content = BypassCloudflareNoCapchaFeachUseCase().execute(f'https://{domain}', url)
                    if content:
                        print(f"[DEBUG] ✓ Conteúdo obtido via BypassCloudflareNoCapchaFeachUseCase - Retornando Response")
                        return Response(200, 'a', content, url)
                    else:
                        print(f"[DEBUG] ✗ BypassCloudflareNoCapchaFeachUseCase retornou None")
                else:
                    print(f"[DEBUG] ✗ Nenhum detector específico ativado, usando fallback")
                    print(f"[DEBUG] → Chamando BypassCloudflareNoCapchaUseCase.execute() [FALLBACK]")
                    content = BypassCloudflareNoCapchaUseCase().execute(url)
                    if content and not IsCloudflareBlockingTimeOutUseCase().execute(content):
                        print(f"[DEBUG] ✓ Conteúdo obtido via BypassCloudflareNoCapchaUseCase (fallback) - Retornando Response")
                        return Response(200, content, content, url)
                    else:
                        print(f"[DEBUG] ✗ BypassCloudflareNoCapchaUseCase (fallback) falhou ou timeout")
                        print(f"[DEBUG] Aguardando 30 segundos...")
                        sleep(30)
                
                print(f"[DEBUG] ========== FIM BYPASS CLOUDFLARE (403) ==========")
                print(f"[DEBUG] Voltando ao loop (tentativa {count}/10)")
                print("")
            elif status not in range(200, 299) and not 403 and not 429:
                print(f"<stroke style='color:#add8e6;'>[REQUEST]:</stroke> <span style='color:#add8e6;'>GET</span> <span style='color:red;'>{status}</span> <a href='#'>{url}</a>")
                sleep(1)
            elif status == 429:
                print(f"<stroke style='color:#add8e6;'>[REQUEST]:</stroke> <span style='color:#add8e6;'>GET</span> <span style='color:#FFFF00;'>{status}</span> <a href='#'>{url}</a>")
                sleep(60)                
            elif status == 301 and 'Location' in response.headers or status == 302 and 'Location' in response.headers:
                print(f"<stroke style='color:#add8e6;'>[REQUEST]:</stroke> <span style='color:#add8e6;'>GET</span> <span style='color:#add8e6;'>{status}</span> <a href='#'>{url}</a>")
                location = response.headers['Location']
                if(location.startswith('https://')):
                    new_url = location
                else:
                    new_url = f'https://{domain}{response.headers['Location']}'
                response = scraper.get(new_url, params=params, headers=headers, cookies=cookies, timeout=None, **kwargs)
                status = response.status_code
            if status in range(200, 299) or status == 404:
                print(f"<stroke style='color:#add8e6;'>[REQUEST]:</stroke> <span style='color:#add8e6;'>GET</span> <span style='color:green;'>{status}</span> <a href='#'>{url}</a>")
                return Response(response.status_code, response.text, response.content, url)

        raise Exception(f"Failed to fetch the URL STATUS: {status}")

    
    @staticmethod
    def post(url, data=None, json=None, headers=None, cookies=None, timeout=None, **kwargs) -> Response:
        status = 0
        count = 0
        extract = tldextract.extract(url)
        domain = f"{extract.domain}.{extract.suffix}"

        scraper = cloudscraper.create_scraper(    
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }    
        )

        while(status not in range(200, 299) and count <= 10):
            count += 1

            request_data = get_request(domain)
            if(request_data):
                re = request_data
                if headers != None: headers = headers | re.headers
                else: headers = re.headers
                if cookies != None: cookies = cookies | re.cookies
                else: cookies = re.cookies
            
            login_data = get_login(domain)

            if login_data:
                re = login_data
                if headers is not None:
                    headers = {**headers, **re.headers}
                else:
                    headers = re.headers
                if cookies is not None:
                    cookies = {**cookies, **re.cookies}
                else:
                    cookies = re.cookies

            response = scraper.post(url, data=data, json=json, headers=headers, cookies=cookies, timeout=timeout, **kwargs)
            status = response.status_code

            if response.status_code == 403:
                print(f"<stroke style='color:#add8e6;'>[REQUEST] POST:</stroke> <span style='color:#add8e6;'>POST</span> <span style='color:#FFFF00;'>{status}</span> <a href='#'>{url}</a>")
                print(f"[DEBUG POST] ========== INÍCIO BYPASS CLOUDFLARE (403) ==========")
                print(f"[DEBUG POST] URL: {url}")
                print(f"[DEBUG POST] Domain: {domain}")
                
                if IsCloudflareBlockingUseCase().execute(response.text):
                    print(f"[DEBUG POST] ✓ IsCloudflareBlockingUseCase DETECTOU bloqueio")
                    print(f"[DEBUG POST] → Chamando BypassCloudflareUseCase.execute()")
                    data = BypassCloudflareUseCase().execute(f'https://{domain}')
                    if data and data.cloudflare_cookie_value:
                        print(f"[DEBUG POST] ✓ Cookie cf_clearance obtido, salvando...")
                        insert_request(RequestData(domain=domain, headers=data.user_agent, cookies=data.cloudflare_cookie_value))
                        print(f"[DEBUG POST] Cookie salvo, voltando ao loop")
                    else:
                        print(f"[DEBUG POST] ✗ Nenhum cookie obtido via BypassCloudflareUseCase")
                        
                elif IsCloudflareEnableCookies().execute(response.text) or IsCloudflareAttention().execute(response.text):
                    print(f"[DEBUG POST] ✓ IsCloudflareEnableCookies ou IsCloudflareAttention DETECTOU problema")
                    print(f"[DEBUG POST] → Chamando BypassCloudflareNoCapchaPostUseCase.execute()")
                    content = BypassCloudflareNoCapchaPostUseCase().execute(f'https://{domain}', url)
                    if content:
                        print(f"[DEBUG POST] ✓ Conteúdo obtido via BypassCloudflareNoCapchaPostUseCase - Retornando Response")
                        return Response(200, 'a', content, url)
                    else:
                        print(f"[DEBUG POST] ✗ BypassCloudflareNoCapchaPostUseCase retornou None")
                else:
                    print(f"[DEBUG POST] ✗ Nenhum detector específico ativado")
                
                print(f"[DEBUG POST] ========== FIM BYPASS CLOUDFLARE (403) ==========")
                print(f"[DEBUG POST] Voltando ao loop (tentativa {count}/10)")
                print("")
            elif status not in range(200, 299) and not 403 and not 429:
                print(f"<stroke style='color:#add8e6;'>[REQUEST] POST:</stroke> <span style='color:#add8e6;'>POST</span> <span style='color:red;'>{status}</span> <a href='#'>{url}</a>")
                sleep(1)
            elif status == 429:
                print(f"<stroke style='color:#add8e6;'>[REQUEST] POST:</stroke> <span style='color:#add8e6;'>POST</span> <span style='color:#FFFF00;'>{status}</span> <a href='#'>{url}</a>")
                sleep(60)
            else:
                print(f"<stroke style='color:#add8e6;'>[REQUEST] POST:</stroke> <span style='color:#add8e6;'>POST</span> <span style='color:green;'>{status}</span> <a href='#'>{url}</a>")
                return Response(response.status_code, response.text, response.content, url)

        raise Exception("Failed to fetch the URL")