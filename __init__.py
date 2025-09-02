#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

__license__ = 'GPL v3'
__copyright__ = '2025, Dein Name <dein@email.de>'
__docformat__ = 'en'

import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from lxml import etree
from calibre.ebooks.metadata.sources.base import Source
from calibre.ebooks.metadata.book.base import Metadata

class SpringerMetadata(Source):
    name = 'Springer'
    description = 'Downloads metadata from Springer Link.'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Invi'
    version = (0, 1, 0)
    minimum_calibre_version = (3, 48, 0)

    capabilities = frozenset(['identify'])
    touched_fields = frozenset(['title', 'authors', 'publisher', 'pubdate', 'languages', 'tags', 'identifier:isbn', 'comments'])
    has_html_comments = True
    can_get_multiple_covers = False
    supports_gzip_transfer_encoding = True
    cached_cover_url_is_reliable = False
    prefer_results_with_isbn = True
    ignore_ssl_errors = True

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        isbn = None
        if identifiers:
            isbn = identifiers.get('isbn', None)
        if not isbn:
            log.info('Springer-Plugin benötigt ISBN.')
            return
        # Springer Link URL bauen
        if isbn:
            url = f'https://link.springer.com/book/{isbn}'
        else:
            log.info('Nur ISBN-Suche ist bisher implementiert.')
            return
        try:
            req = Request(url)
            try:
                with urlopen(req, timeout=timeout) as response:
                    html = response.read()
            except HTTPError as e:
                log.info(f'Fehler beim Abrufen der Seite: {e.code}')
                return
            parser = etree.HTMLParser()
            tree = etree.fromstring(html, parser)
            # Bibliographic Section
            bib_section = tree.xpath("//section[@data-title='Bibliographic Information']")
            bib_items = bib_section[0].xpath(".//li[contains(@class, 'c-bibliographic-information__list-item')]") if bib_section else []
            meta = {}
            for item in bib_items:
                label = item.xpath(".//span[contains(@class, 'u-text-bold')]")
                value = item.xpath(".//span[contains(@class, 'c-bibliographic-information__value')]")
                label_text = label[0].text.strip() if label else None
                value_text = value[0].xpath('string()').strip() if value else None
                if label_text and value_text:
                    meta[label_text] = value_text
                # ISBNs und Datum
                if label_text and 'ISBN' in label_text:
                    date_span = item.xpath(".//span[contains(@data-test, 'publication_date')]")
                    if date_span:
                        meta[label_text + ' Date'] = date_span[0].text.replace('Published:', '').strip()
            # Titel, Untertitel
            title = meta.get('Book Title', 'Unbekannt')
            subtitle = meta.get('Book Subtitle', '')
            if subtitle:
                title = f"{title}: {subtitle}"
            # Autoren/Herausgeber
            editors = meta.get('Editors', '')
            # Split only on ',' if present, otherwise treat as single name
            log.info(f"Editors: {editors}")
            if "," in editors:
                authors = [a.strip() for a in editors.split(',')]
            else:
                authors = [editors.strip()] if editors else []
            authors_str = ', '.join(authors)
            log.info(f"Authors: {authors_str}")
            # DOI
            doi = meta.get('DOI', '')
            # Verlag
            publisher = meta.get('Publisher', 'Springer')
            # Erscheinungsdatum
            pubdate_str = meta.get('eBook ISBN Date', '') or meta.get('Softcover ISBN Date', '')
            pubdate = None
            if pubdate_str:
                import datetime
                # Versuche verschiedene Formate zu parsen
                try:
                    # Format: '30 August 2025'
                    pubdate = datetime.datetime.strptime(pubdate_str, '%d %B %Y')
                except Exception:
                    try:
                        # Format: 'August 2025'
                        pubdate = datetime.datetime.strptime(pubdate_str, '%B %Y')
                    except Exception:
                        try:
                            # Format: '2025'
                            pubdate = datetime.datetime.strptime(pubdate_str, '%Y')
                        except Exception:
                            pubdate = None
            # Sprache (Springer meist Deutsch, kann aber auch Englisch sein)
            languages = ['de']
            # Schlagwörter/Themen
            topics = []
            for item in bib_items:
                label = item.xpath(".//span[contains(@class, 'u-text-bold')]")
                label_text = label[0].text.strip() if label else None
                if label_text == 'Topics':
                    topics_links = item.xpath(".//a")
                    topics = [a.text.strip() for a in topics_links]
            tags = topics
            # Beschreibung aus "About this book"
            about_section = tree.xpath("//section[@data-title='About this book']")
            comments = ''
            if about_section:
                about_div = about_section[0].xpath(".//div[contains(@class, 'c-book-section')]")
                if about_div:
                    comments = etree.tostring(about_div[0], encoding='unicode', method='html')
            # Metadatenobjekt
            mi = Metadata(title, authors_str)
            mi.publisher = publisher
            mi.pubdate = pubdate
            mi.languages = languages
            mi.comments = comments
            mi.isbn = isbn
            mi.identifiers = {'doi': doi, 'isbn': isbn}
            mi.tags = tags
            result_queue.put(mi)
        except Exception as e:
            log.info(f'Fehler: {e}')
            return
