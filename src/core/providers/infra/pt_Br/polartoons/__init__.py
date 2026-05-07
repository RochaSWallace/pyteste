import re
from typing import List, Tuple
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup

from core.__seedwork.infra.http import Http
from core.providers.domain.entities import Chapter, Manga, Pages
from core.providers.infra.template.wordpress_madara import WordPressMadara


class PolartoonsProvider(WordPressMadara):
	name = 'Polar Toons'
	lang = 'pt_Br'
	domain = ['polartoons.net', 'www.polartoons.net']

	def __init__(self):
		self.url = 'https://polartoons.net/'
		self.path = ''

		self.query_mangas = 'div.post-title h3 a, div.post-title h5 a'
		self.query_chapters = '#chaptersTabs a, .chapters-wrapper a'
		self.query_chapters_title_bloat = None
		self.query_pages = 'div.image-wrapper'
		self.query_title_for_uri = 'h1.obra-title'
		self.query_placeholder = None
		self.timeout = None

	def getManga(self, link: str) -> Manga:
		response = Http.get(link, timeout=getattr(self, 'timeout', None))
		soup = BeautifulSoup(response.content, 'html.parser')

		element = (
			soup.select_one(self.query_title_for_uri)
			or soup.select_one('h1')
			or soup.select_one('head meta[property="og:title"]')
			or soup.select_one('title')
		)
		title = link
		if element:
			title = element['content'].strip() if 'content' in element.attrs else element.get_text(strip=True)

		return Manga(id=link, name=title)

	def getChapters(self, id: str) -> List[Chapter]:
		uri = urljoin(self.url, id)
		response = Http.get(uri, timeout=getattr(self, 'timeout', None))
		soup = BeautifulSoup(response.content, 'html.parser')

		element = (
			soup.select_one(self.query_title_for_uri)
			or soup.select_one('h1')
			or soup.select_one('head meta[property="og:title"]')
			or soup.select_one('title')
		)
		title = element['content'].strip() if element and 'content' in element.attrs else (element.get_text(strip=True) if element else uri)

		chapter_items = self._extract_chapters_from_script(soup)
		if not chapter_items:
			chapter_items = self._extract_chapters_from_dom(soup, uri)

		seen = set()
		chapters = []
		for ch_id, ch_number in chapter_items:
			if not ch_id or ch_id in seen:
				continue
			seen.add(ch_id)
			chapters.append(Chapter(ch_id, ch_number, title))

		chapters.reverse()
		return chapters

	def getPages(self, ch: Chapter) -> Pages:
		uri = urljoin(self.url, ch.id)
		soup = self._get_chapter_soup(uri)

		entries = []
		for element in soup.select(self.query_pages):
			entries.append(self._process_page_element(element, uri))

		if not entries:
			for img in soup.select('img.lozad, .content-webtoon img'):
				src = img.get('data-url') or img.get('data-src') or img.get('srcset') or img.get('src')
				if not src:
					continue
				if 'data:image' in src:
					entries.append(src.split()[0])
				else:
					entries.append(self.create_connector_uri({'url': urljoin(uri, src), 'referer': uri}))

		number = self._extract_number(str(ch.number))
		return Pages(ch.id, number, ch.name, entries)

	def _get_chapter_soup(self, uri: str) -> BeautifulSoup:
		try:
			response = Http.get(uri, timeout=getattr(self, 'timeout', None))
			return BeautifulSoup(response.content, 'html.parser')
		except Exception:
			scraper = cloudscraper.create_scraper(
				browser={
					'browser': 'chrome',
					'platform': 'windows',
					'mobile': False,
				}
			)
			response = scraper.get(uri, timeout=getattr(self, 'timeout', None))
			return BeautifulSoup(response.content, 'html.parser')

	def _extract_chapters_from_script(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
		for script in soup.find_all('script'):
			script_text = script.get_text() or ''
			if 'const chaptersData' not in script_text:
				continue

			array_match = re.search(
				r'const\s+chaptersData\s*=\s*\[(?P<data>[\s\S]*?)\]\s*;',
				script_text,
			)
			if not array_match:
				continue

			entries = []
			for block in re.findall(r'\{[\s\S]*?\}', array_match.group('data')):
				url_match = re.search(r'url\s*:\s*["\']([^"\']+)["\']', block)
				if not url_match:
					continue

				num_match = re.search(r'num\s*:\s*([0-9]+(?:\.[0-9]+)?)', block)
				title_match = re.search(r'title\s*:\s*["\']([^"\']+)["\']', block)

				raw_number = num_match.group(1) if num_match else (title_match.group(1) if title_match else '')
				ch_number = self._extract_number(raw_number)
				entries.append((url_match.group(1).strip(), ch_number))

			if entries:
				return entries

		return []

	def _extract_chapters_from_dom(self, soup: BeautifulSoup, base_uri: str) -> List[Tuple[str, str]]:
		entries = []
		for element in soup.select(self.query_chapters):
			ch_id = self.get_root_relative_or_absolute_link(element, base_uri)
			if not ch_id:
				continue

			raw_text = ' '.join(element.get_text(' ', strip=True).split())
			ch_number = self._extract_number(raw_text)
			entries.append((ch_id, ch_number))

		return entries

	def _extract_number(self, text: str) -> str:
		match = re.search(r'\d+(?:\.\d+)?', str(text))
		return match.group(0) if match else str(text).strip()
