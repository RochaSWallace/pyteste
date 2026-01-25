from core.providers.infra.template.blogger_cms import BloggerCms

class ScanPinkRosaProvider(BloggerCms):
    name = 'Scan Pink Rosa'
    lang = 'pt-Br'
    domain = ['scanpinkrosa.blogspot.com']
    has_login = False

    def __init__(self):
        self.get_title = 'h1#post-title'
        self.API_domain = 'scanpinkrosa.blogspot.com'
        self.get_pages = 'div.separator a img'
