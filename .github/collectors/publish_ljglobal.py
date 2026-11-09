"""Publish licensed articles and raster images after explicit user authorization."""
import argparse
import base64
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urlunsplit, quote
from urllib.request import Request, build_opener
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET
import ljglobal as C

MODE = 'authorized-full-v1'
MANIFEST = '.github/collectors/published-ljglobal.json'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
BLOCKED = {'script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'button', 'select', 'video', 'audio', 'noscript', 'nav', 'header', 'footer', 'aside', 'svg', 'link', 'meta'}
ALLOWED = {'p', 'div', 'span', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'blockquote', 'strong', 'b', 'em', 'i', 'u', 'small', 'sub', 'sup', 'br', 'hr', 'pre', 'code', 'figure', 'figcaption'}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    start: int = 0
    inner_start: int = 0
    inner_end: int = 0
    end: int = 0

    def has_class(self, value):
        return value in self.attrs.get('class', '').split()

    def text(self):
        return ''.join(x.text() if isinstance(x, Node) else x for x in self.children)

    def find(self, predicate):
        if predicate(self):
            return self
        for child in self.children:
            if isinstance(child, Node):
                found = child.find(predicate)
                if found:
                    return found
        return None

    def all(self, predicate):
        found = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.all(predicate))
        return found


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        for match in re.finditer('\n', source):
            self.lines.append(match.end())
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(source)
        self.close()
        for node in self.stack[1:]:
            node.inner_end = node.end = len(source)

    def source_index(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.source_index()
        end = start + len(self.get_starttag_text())
        node = Node(tag, dict(attrs), start=start, inner_start=end, inner_end=end, end=end)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag and tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                start = self.source_index()
                end = self.source.find('>', start) + 1
                for node in self.stack[i:]:
                    node.inner_end = start
                    node.end = end
                self.stack = self.stack[:i]
                return

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def replace_ranges(source, edits):
    edits = sorted(edits, key=lambda e: e[0], reverse=True)
    previous = len(source) + 1
    for start, end, replacement in edits:
        if start < 0 or end > len(source) or start >= end or end > previous:
            raise ValueError('Overlapping or invalid template edits')
        source = source[:start] + replacement + source[end:]
        previous = start
    return source


class Reader:
    def __init__(self, config):
        self.config = config
        self.rules = {}
        self.cache = {}

    def raw(self, url, limit):
        parts = urlsplit(url)
        permitted = {self.config['source_host'], *self.config['image_hosts']}
        if parts.scheme != 'https' or parts.netloc not in permitted:
            raise ValueError('Resource is outside the authorized HTTPS source/image hosts')
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
            raise ValueError('Resource DNS resolved to a non-public address')
        encoded = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%:@-._~!$&'()*+,;="), quote(parts.query, safe="%=&/:?+"), ''))
        request = Request(encoded, headers={'User-Agent': C.AGENT, 'Accept-Encoding': 'identity'})
        try:
            with build_opener(C.NoRedirect).open(request, timeout=25) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Resource exceeds configured size limit')
                return response.status, data
        except HTTPError as exc:
            if parts.path == '/robots.txt' and exc.code in (404, 410):
                return exc.code, b''
            raise RuntimeError(f'Authorized source resource returned HTTP {exc.code}; not bypassed') from None

    def get(self, url, image=False):
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self.rules:
            status, data = self.raw('https://' + host + '/robots.txt', C.LIMIT)
            rp = RobotFileParser()
            if status == 200:
                rp.parse(data.decode('utf-8-sig').splitlines())
            elif status in (404, 410):
                rp.parse([])
            else:
                raise ValueError('Cannot verify robots.txt for the resource host')
            self.rules[host] = rp
        if not self.rules[host].can_fetch(C.AGENT, url):
            raise ValueError('robots.txt disallows an authorized source resource')
        if url not in self.cache:
            status, data = self.raw(url, 8 * 1024 * 1024 if image else C.LIMIT)
            if status != 200:
                raise ValueError('Source resource did not return HTTP 200')
            self.cache[url] = data
        return self.cache[url]


def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[4:8] == b'ftyp' and b'avif' in data[8:32]:
        return 'avif'
    raise ValueError('Image is not a supported raster file; SVG/HTML are not published')


def load_config(repo):
    config = json.loads((repo / '.github/collectors/ljglobal-rights.json').read_text(encoding='utf-8'))
    if not all(config.get(k) is True for k in ('enabled', 'authorization_confirmed_by_user', 'full_text', 'original_images')):
        raise ValueError('Authorized full publication is disabled or authorization is not confirmed')
    if config['source_host'] != 'www.ljglobal.cn' or not set(config['image_hosts']).issubset({'www.ljglobal.cn', 'lingjuimg.com'}):
        raise ValueError('Unexpected source/image hosts; inspect configuration')
    return config


def promotional(node):
    value = C.plain(node.text())
    if node.tag in ('p', 'figcaption') and re.match(r'^(文章来源|文章出处|原文链接|版权声明|本文来自|责任编辑|作者[:：])', value):
        return True
    if node.tag == 'p' and node.find(lambda n: n.tag == 'a' and (re.search(r'/(contact|contact-us)(/|$)', urlsplit(n.attrs.get('href') or '').path) or (n.attrs.get('href') or '').lower().startswith(('tel:', 'mailto:', 'https://wa.me/')))):
        return True
    return any(re.search(r'(^|[-_])(qrcode|contact-form|share|social)([-_]|$)', item, re.I) for item in node.attrs.get('class', '').split())


def image_source(attrs):
    for name in ('data-orig-file', 'data-original', 'data-full-url'):
        if attrs.get(name):
            return attrs[name]
    candidates = []
    for candidate in (attrs.get('srcset') or '').split(','):
        match = re.fullmatch(r'\s*(\S+)\s+(\d+(?:\.\d+)?)(w|x)\s*', candidate)
        if match:
            candidates.append((float(match[2]), match[1]))
    if candidates:
        return max(candidates)[1]
    return attrs.get('data-src') or attrs.get('src')


def clean_article(article, url, reader):
    files, images, source_images = {}, [], {}

    def render(node):
        if isinstance(node, str):
            return html.escape(node)
        if node.tag in BLOCKED or promotional(node):
            return ''
        if node.tag == 'img':
            attrs = node.attrs
            if attrs.get('width') == '1' or attrs.get('height') == '1' or re.search(r'二维码|扫码|关注公众号|联系顾问', attrs.get('alt') or ''):
                return ''
            raw = image_source(attrs)
            if not raw:
                raise ValueError('Article image has no usable URL')
            image_url = urljoin(url, raw)
            if len(images) >= 24 and image_url not in source_images:
                raise ValueError('Article contains more than 24 images; review before raising limit')
            if image_url not in source_images:
                data = reader.get(image_url, image=True)
                ext = image_extension(data)
                digest = hashlib.sha256(data).hexdigest()
                relative = 'assets/images/imported/ljglobal/' + digest[:24] + '.' + ext
                files[relative] = data
                source_images[image_url] = relative
                images.append({'file': relative, 'sha256': digest, 'bytes': len(data)})
            relative = source_images[image_url]
            extra = ''
            for name in ('width', 'height'):
                value = attrs.get(name) or ''
                if re.fullmatch(r'[1-9][0-9]{0,4}', value):
                    extra += f' {name}="{value}"'
            alt = html.escape((attrs.get('alt') or '')[:300], quote=True)
            local = '../' + relative
            return f'<a href="{local}" target="_blank" rel="noopener noreferrer"><img src="{local}" alt="{alt}"{extra} loading="lazy" decoding="async"></a>'
        content = ''.join(render(child) for child in node.children)
        if node.tag == 'a' or node.tag not in ALLOWED:
            return content
        extra = ''
        if node.tag in ('td', 'th'):
            for name in ('colspan', 'rowspan'):
                value = node.attrs.get(name) or ''
                if re.fullmatch(r'[1-9][0-9]?', value):
                    extra += f' {name}="{value}"'
        return '<' + node.tag + extra + '>' + ('' if node.tag in VOID else content + '</' + node.tag + '>')

    body = ''.join(render(child) for child in article.children)
    if len(C.plain(body)) < 200:
        raise ValueError('Article body is unexpectedly short after sanitization')
    if re.search(r'<(?:script|iframe|form)\b|\son\w+=|https?://', body, re.I):
        raise ValueError('Unsafe or external URL content remains; hold this article for review')
    return body, files, images


def extract_article(source, item, reader):
    tree = Tree(source).root
    article = tree.find(lambda n: n.tag == 'article' and n.has_class('nnn_article'))
    heading = tree.find(lambda n: n.tag == 'h1')
    canonical = tree.find(lambda n: n.tag == 'link' and n.attrs.get('rel') == 'canonical')
    if not article or not heading or not canonical:
        raise ValueError('Source article template is not recognized')
    if C.canonical_url(canonical.attrs.get('href', '')) != item['url']:
        raise ValueError('Source canonical does not match the requested article')
    title = C.plain(heading.text())[:180]
    body, files, images = clean_article(article, item['url'], reader)
    description = C.plain(body)[:155]
    try:
        published = C.iso(parsedate_to_datetime(item['published']))
    except (ValueError, TypeError):
        raise ValueError('Cannot verify original publication date') from None
    return {'id': item['id'], 'source_url': item['url'], 'title': title, 'description': description,
            'category': item['category'], 'body': body, 'published_at': published,
            'file': 'pages/' + urlsplit(item['url']).path.strip('/') + '.html',
            'images': images}, files


def metadata_edits(template, record, date):
    tree = Tree(template).root
    title = tree.find(lambda n: n.tag == 'title')
    if not title:
        raise ValueError('Article template has no title')
    edits = [(title.start, title.end, '<title>' + html.escape(record['title']) + '</title>')]
    for node in tree.all(lambda n: n.tag == 'meta'):
        if node.attrs.get('name') in ('description', 'keywords', 'twitter:card', 'twitter:title', 'twitter:description', 'twitter:image') or (node.attrs.get('property') or '').startswith('og:'):
            edits.append((node.start, node.end, ''))
    for node in tree.all(lambda n: n.tag == 'link' and n.attrs.get('rel') == 'canonical'):
        edits.append((node.start, node.end, ''))
    for node in tree.all(lambda n: n.tag == 'script' and n.attrs.get('type') == 'application/ld+json'):
        edits.append((node.start, node.end, ''))
    result = replace_ranges(template, edits)
    canonical = 'https://chaudizhi.com/' + record['file']
    esc = lambda s: html.escape(str(s), quote=True)
    tags = f'<meta name="description" content="{esc(record["description"])}"><link rel="canonical" href="{canonical}"><meta property="og:type" content="article"><meta property="og:title" content="{esc(record["title"])}"><meta property="og:description" content="{esc(record["description"])}"><meta property="og:url" content="{canonical}"><meta name="twitter:card" content="summary_large_image"><link rel="stylesheet" href="../assets/css/imported-articles.css">'
    schema = {'@context': 'https://schema.org', '@type': 'Article', 'headline': record['title'],
              'description': record['description'], 'inLanguage': 'zh-CN', 'mainEntityOfPage': canonical,
              'datePublished': record['published_at'], 'dateModified': date}
    if record['images']:
        image = 'https://chaudizhi.com/' + record['images'][0]['file']
        tags += f'<meta property="og:image" content="{image}">'
        schema['image'] = [image]
    tags += '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
    return result.replace('</head>', tags + '</head>', 1)


def render_page(template, record, date):
    tree = Tree(template).root
    old_body = tree.find(lambda n: n.has_class('blog-details-area'))
    if not old_body:
        raise ValueError('Website article template has changed')
    stamp = record['published_at'][:10]
    content = f'<main class="seo-content-section authorized-article"><div class="container"><article><p class="article-meta">{html.escape(record["category"])} · <time datetime="{record["published_at"]}">{stamp}</time></p><h1>{html.escape(record["title"])}</h1><div class="authorized-article-body">{record["body"]}</div><div class="article-next"><a href="blog-grid.html">返回文章列表</a></div></article></div></main>'
    removed = tree.all(lambda n: n.has_class('breadcumb-area') or n.has_class('seo-content-section'))
    edits = [(old_body.start, old_body.end, content)] + [(n.start, n.end, '') for n in removed]
    page = replace_ranges(template, edits)
    page = metadata_edits(page, record, date)
    if 'www.ljglobal.cn' in page or 'lingjuimg.com' in page:
        raise ValueError('Original host remains in public page')
    if len(Tree(page).root.all(lambda n: n.tag == 'h1')) != 1:
        raise ValueError('Rendered page does not have one main heading')
    return page


def card(record, home=False):
    title, desc = html.escape(record['title']), html.escape(record['description'])
    href = record['file'] if home else record['file'].removeprefix('pages/')
    image = record['images'][0]['file'] if record['images'] else None
    src = image if home else '../' + image if image else None
    img = f'<img src="{src}" alt="{title}" loading="lazy" decoding="async">' if src else ''
    if home:
        return f'<div class="col-lg-12 col-md-12"><div class="single-blog-box"><div class="single-blog-thumb">{img}</div><div class="blog-content"><div class="blog-meta-top"><h5>{html.escape(record["category"])}</h5><h6>{record["published_at"][:10]}</h6></div><h3><a href="{href}">{title}</a></h3><div class="blog-button"><a href="{href}">阅读全文<i class="carousel-arrow-right"></i></a></div></div></div></div>'
    if img:
        img = img.replace('<img ', '<img class="seo-article-image" ', 1)
    return f'<div class="col-lg-4 col-md-6"><div class="platform-info-card">{img}<span class="platform-kicker">{html.escape(record["category"])} · {record["published_at"][:10]}</span><h2 class="seo-card-title"><a href="{href}">{title}</a></h2><p>{desc}</p><a href="{href}">阅读全文 →</a></div></div>'


def update_listing(source, records):
    tree = Tree(source).root
    section = tree.find(lambda n: n.has_class('seo-content-section'))
    grid = section.find(lambda n: n.has_class('row')) if section else None
    if not grid:
        raise ValueError('Article list template no longer matches')
    return source[:grid.inner_start] + ''.join(card(r) for r in records) + source[grid.inner_start:]


def update_home(source, entries):
    tree = Tree(source).root
    carousel = tree.find(lambda n: n.has_class('blog-list-3'))
    if not carousel:
        raise ValueError('Homepage latest-articles module no longer matches')
    candidates = {}
    for node in carousel.children:
        if not isinstance(node, Node):
            continue
        heading = node.find(lambda n: n.tag == 'h3')
        link = heading.find(lambda n: n.tag == 'a') if heading else None
        date_node = node.find(lambda n: n.tag == 'h6')
        stamp = date_node.text().strip() if date_node else ''
        if link and re.fullmatch(r'\d{4}-\d{2}-\d{2}', stamp):
            candidates[link.attrs.get('href')] = (stamp, '', source[node.start:node.end])
    for record in entries:
        candidates[record['file']] = (record['published_at'][:10], record['imported_at'], card(record, True))
    newest = sorted(candidates.values(), key=lambda value: value[:2], reverse=True)[:4]
    return replace_ranges(source, [(carousel.inner_start, carousel.inner_end, ''.join(value[2] for value in newest))])


def update_sitemap(source, records, date):
    if re.search(r'<!DOCTYPE|<!ENTITY', source, re.I):
        raise ValueError('Unexpected sitemap entity declaration')
    ET.register_namespace('', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    root = ET.fromstring(source)
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    if root.tag != ns + 'urlset':
        raise ValueError('Expected sitemap urlset')
    urls = {node.findtext(ns + 'loc'): node for node in root.findall(ns + 'url')}
    for record in records:
        url = 'https://chaudizhi.com/' + record['file']
        if url in urls:
            raise ValueError('New article already appears in sitemap')
        node = ET.SubElement(root, ns + 'url')
        ET.SubElement(node, ns + 'loc').text = url
        ET.SubElement(node, ns + 'lastmod').text = date[:10]
    for url in ('https://chaudizhi.com/', 'https://chaudizhi.com/pages/blog-grid.html'):
        if url in urls:
            stamp = urls[url].find(ns + 'lastmod')
            if stamp is None:
                stamp = ET.SubElement(urls[url], ns + 'lastmod')
            stamp.text = date[:10]
    return ET.tostring(root, encoding='unicode', xml_declaration=True)


def read_manifest(repo):
    file = repo / MANIFEST
    if not file.exists():
        return {'version': 1, 'entries': {}}
    value = json.loads(file.read_text(encoding='utf-8'))
    if value.get('version') != 1 or not isinstance(value.get('entries'), dict):
        raise ValueError('Publication manifest is invalid; do not reset it')
    for key, record in value['entries'].items():
        if not re.fullmatch(r'[a-f0-9]{64}', key) or not re.fullmatch(r'pages/[a-z0-9]+(?:-[a-z0-9]+)*\.html', record.get('file', '')):
            raise ValueError('Publication manifest contains invalid identity/path')
    return value


def build_stage(repo, items, reader, date, limit=10):
    manifest = read_manifest(repo)
    entries = manifest['entries']
    template = (repo / 'pages/google-ads-management-fees.html').read_text(encoding='utf-8')
    files, records, failures = {}, [], []
    for item in [i for i in items if i['id'] not in entries][:limit]:
        try:
            slug = urlsplit(item['url']).path.strip('/')
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
                raise ValueError('Source slug needs manual mapping')
            filename = 'pages/' + slug + '.html'
            if (repo / filename).exists():
                raise ValueError('Target file already exists without a publication record; not overwritten')
            record, images = extract_article(reader.get(item['url']).decode('utf-8-sig'), item, reader)
            record['imported_at'] = date
            page = render_page(template, record, date)
            files[record['file']] = page.encode('utf-8')
            files.update(images)
            record['content_sha256'] = hashlib.sha256(page.encode()).hexdigest()
            del record['body']
            entries[item['id']] = record
            records.append(record)
        except (ValueError, RuntimeError, OSError, UnicodeError) as exc:
            failures.append({'source_id': item['id'], 'title': item['title'], 'error': str(exc)})
    if records:
        files['pages/blog-grid.html'] = update_listing((repo / 'pages/blog-grid.html').read_text(encoding='utf-8'), records).encode()
        files['index.html'] = update_home((repo / 'index.html').read_text(encoding='utf-8'), list(entries.values())).encode()
        files['sitemap.xml'] = update_sitemap((repo / 'sitemap.xml').read_text(encoding='utf-8'), records, date).encode()
        files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return files, records, failures, manifest


def publish_commit(api, repo, files):
    current = api.api('GET', '/git/ref/heads/main')['object']['sha']
    local = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if current != local:
        raise ValueError('Main changed during collection; not overwriting concurrent changes')
    if not files:
        return current
    base = api.api('GET', '/git/commits/' + current)['tree']['sha']
    elements = []
    for name, data in files.items():
        if not (re.fullmatch(r'pages/[a-z0-9-]+\.html', name) or re.fullmatch(r'assets/images/imported/ljglobal/[a-f0-9]{24}\.(png|jpg|webp|gif|avif)', name) or name in ('index.html', 'sitemap.xml', MANIFEST)):
            raise ValueError('Publication tried to write an unexpected path')
        blob = api.api('POST', '/git/blobs', {'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
        elements.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    tree = api.api('POST', '/git/trees', {'base_tree': base, 'tree': elements})
    commit = api.api('POST', '/git/commits', {'message': 'Publish authorized ljglobal articles and local original images', 'tree': tree['sha'], 'parents': [current]})
    api.api('PATCH', '/git/refs/heads/main', {'sha': commit['sha'], 'force': False})
    return commit['sha']


def emit(values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as handle:
            for key, value in values.items():
                if '\n' in str(value) or '\r' in str(value):
                    raise ValueError('Unexpected multiline workflow output')
                handle.write(f'{key}={value}\n')


def finalize(repo):
    api = C.GitHubState()
    state, sha, existed = api.load()
    expected = os.environ.get('EXPECTED_STATE_SHA', 'missing')
    if (sha or 'missing') != expected:
        raise ValueError('State changed while deploying; not advancing its cursor')
    if os.environ.get('HAS_FAILURES') == 'true':
        raise ValueError('Some articles were held; published successes remain, cursor not advanced so next daily check retries')
    manifest = read_manifest(repo)
    ids = set(state['seen_ids']) | set(manifest['entries'])
    if len(ids) > 10000:
        raise ValueError('Publication state reached its deliberate archive limit')
    observed = os.environ['COLLECTION_TIME']
    C.parse_time(observed)
    next_state = {'version': 1, 'last_success': observed, 'seen_ids': sorted(ids), 'publication_mode': MODE,
                  'deployed_sha': os.environ['PUBLISHED_SHA']}
    api.persist({'expected_sha': sha, 'branch_existed': existed, 'next_state': next_state})
    C.summary('Authorized articles were deployed; 72-hour cursor advanced only after Pages success.')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--out', type=Path, default=Path('publisher-output'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--local-state', type=Path)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    config = load_config(repo)
    if args.finalize:
        finalize(repo)
        return 0
    if args.local_state:
        if not args.dry_run:
            raise ValueError('Local state is permitted only with --dry-run')
        state = C.validate_state(json.loads(args.local_state.read_text(encoding='utf-8'))) if args.local_state.exists() else C.initial_state()
        expected_sha = None
    else:
        api = C.GitHubState()
        state, expected_sha, _ = api.load()
    now = C.now_utc()
    bootstrap = state.get('publication_mode') != MODE
    if not C.due(state, now, args.force or bootstrap):
        emit({'collected': 'false'})
        C.summary('Skipped: fewer than 72 hours since the last successful full publication.')
        return 0
    items = C.collect_source(now=now)
    files, records, failures, manifest = build_stage(repo, items, Reader(config), C.iso(now), min(args.limit, config['max_articles_per_run']))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = args.out / 'site-files' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    report = {'collected_at': C.iso(now), 'source_feed_items': len(items), 'new_articles': len(records),
              'new_image_files': len([n for n in files if n.startswith('assets/images/')]),
              'articles': [{'title': r['title'], 'url': 'https://chaudizhi.com/' + r['file'], 'images': len(r['images'])} for r in records],
              'failures': failures, 'dry_run': args.dry_run}
    (args.out / 'publication-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    C.summary(f"Authorized full publication prepared: {len(records)} new articles, {report['new_image_files']} raster images, {len(failures)} held articles.")
    if args.dry_run:
        return 1 if failures else 0
    if failures and not records and not all(i['id'] in manifest['entries'] for i in items):
        raise ValueError('No new articles were safely prepared; inspect the artifact report')
    published_sha = publish_commit(api, repo, files)
    emit({'collected': 'true', 'published_sha': published_sha, 'expected_state_sha': expected_sha or 'missing',
          'collection_time': C.iso(now), 'has_failures': 'true' if failures else 'false'})
    C.summary('Website commit prepared for explicit Pages deployment: ' + published_sha)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, ET.ParseError, subprocess.SubprocessError) as exc:
        C.summary('Authorized publication stopped; deployment cursor not advanced: ' + html.escape(str(exc)))
        sys.exit(1)
