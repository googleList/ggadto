"""Collect public RSS topic metadata, not article bodies or images."""
import argparse
import base64
import hashlib
import html
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

FEED = 'https://www.ljglobal.cn/category/news/feed/'
CATEGORY = 'https://www.ljglobal.cn/category/news/'
ROBOTS = 'https://www.ljglobal.cn/robots.txt'
AGENT = 'ChaudizhiTopicCollector/1.0'
BRANCH = 'collector-state'
STATE_PATH = '.collector/ljglobal-state.json'
INTERVAL = timedelta(hours=72)
LIMIT = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.blocked = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.blocked:
            self.blocked -= 1

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def plain(value):
    parser = TextOnly()
    parser.feed(value or '')
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def now_utc():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('State timestamp must include a timezone')
    return result


def due(state, now, force=False):
    if force or not state.get('last_success'):
        return True
    previous = parse_time(state['last_success'])
    if previous > now + timedelta(hours=1):
        raise ValueError('State timestamp is in the future; inspect state before continuing')
    return now - previous >= INTERVAL


def canonical_url(value):
    u = urlsplit(value.strip())
    if u.scheme != 'https' or u.netloc != 'www.ljglobal.cn' or not u.path.startswith('/'):
        raise ValueError('Feed item is not a canonical HTTPS URL on the configured source')
    params = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
              if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid')]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(params), ''))


def category(title, excerpt):
    value = title + ' ' + excerpt
    if re.search(r'(?<![A-Za-z])GEO(?![A-Za-z])|AI\s*(?:Overview|Mode|搜索)|生成式|人工智能|大模型', value, re.I):
        return 'GEO'
    if re.search(r'(?<![A-Za-z])Ads(?![A-Za-z])|(?<![A-Za-z])SEM(?![A-Za-z])|PMax|PPC|广告|出价|代投', value, re.I):
        return 'Ads'
    if re.search(r'SEO|搜索引擎|谷歌|Google|独立站', value, re.I):
        return 'SEO'
    return '资讯'


def child_text(node, names):
    for child in node:
        if child.tag.split('}')[-1] in names:
            return ''.join(child.itertext()).strip()
    return ''


def parse_feed(text, observed_at):
    if re.search(r'<!DOCTYPE|<!ENTITY', text, re.I):
        raise ValueError('XML entity and DOCTYPE declarations are not accepted')
    root = ET.fromstring(text)
    if root.tag.split('}')[-1] != 'rss':
        raise ValueError('Configured source did not return an RSS feed')
    nodes = root.findall('./channel/item')
    if not nodes:
        raise ValueError('Feed contains no items; do not silently advance the cursor')
    if len(nodes) > 100:
        raise ValueError('Unexpected feed size; inspect source before changing limits')
    items, seen = [], set()
    for node in nodes:
        title = plain(child_text(node, {'title'}))[:220]
        link = canonical_url(child_text(node, {'link'}))
        digest = hashlib.sha256(link.encode()).hexdigest()
        if not title or digest in seen:
            continue
        seen.add(digest)
        excerpt = plain(child_text(node, {'description', 'summary'}))[:350]
        items.append({'id': digest, 'title': title, 'url': link,
                      'excerpt': excerpt, 'published': child_text(node, {'pubDate'})[:80],
                      'category': category(title, excerpt),
                      'source': 'ljglobal-news', 'collected_at': observed_at})
    if not items:
        raise ValueError('No usable metadata items were parsed')
    return items


def source_fetch(url):
    if url not in (FEED, ROBOTS):
        raise ValueError('Only the configured robots and RSS endpoints can be fetched')
    addresses = socket.getaddrinfo('www.ljglobal.cn', 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Source DNS resolved to a non-public address')
    req = Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/rss+xml, application/xml, text/plain', 'Accept-Encoding': 'identity'})
    try:
        with build_opener(NoRedirect).open(req, timeout=25) as response:
            data = response.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError('Source response exceeds 2MB')
            return response.status, data.decode('utf-8-sig')
    except HTTPError as exc:
        if url == ROBOTS and exc.code in (404, 410):
            return exc.code, ''
        raise RuntimeError(f'Source returned HTTP {exc.code}; no bypass or state advance') from None


def collect_source(fetcher=source_fetch, now=None):
    now = now or now_utc()
    status, rules = fetcher(ROBOTS)
    if status not in (200, 404, 410):
        raise ValueError('robots.txt could not be verified')
    if status == 200:
        rp = RobotFileParser()
        rp.parse(rules.splitlines())
        if not rp.can_fetch(AGENT, FEED):
            raise ValueError('robots.txt disallows the feed')
    status, text = fetcher(FEED)
    if status != 200:
        raise ValueError('Feed did not return HTTP 200')
    return parse_feed(text, iso(now))


def initial_state():
    return {'version': 1, 'last_success': None, 'seen_ids': []}


def validate_state(state):
    if state.get('version') != 1 or not isinstance(state.get('seen_ids'), list):
        raise ValueError('Unsupported or malformed state; refusing to reset deduplication')
    if any(not isinstance(s, str) or not re.fullmatch(r'[a-f0-9]{64}', s) for s in state['seen_ids']):
        raise ValueError('Invalid deduplication IDs')
    if state.get('last_success'):
        parse_time(state['last_success'])
    return state


class GitHubState:
    def __init__(self, repository=None, token=None):
        self.repository = repository or os.environ.get('GITHUB_REPOSITORY', '')
        self.token = token if token is not None else os.environ.get('GH_TOKEN', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repository):
            raise ValueError('GITHUB_REPOSITORY is missing or invalid')

    def api(self, method, suffix, payload=None, missing_ok=False):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': AGENT,
                   'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = Request('https://api.github.com/repos/' + self.repository + suffix, data=data, headers=headers, method=method)
        try:
            with build_opener(NoRedirect).open(req, timeout=25) as response:
                return json.load(response)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise RuntimeError(f'GitHub {method} failed with HTTP {exc.code}; check Actions contents permission and state conflicts') from None

    def load(self):
        ref = self.api('GET', '/git/ref/heads/' + BRANCH, missing_ok=True)
        if ref is None:
            return initial_state(), None, False
        content = self.api('GET', '/contents/' + STATE_PATH + '?ref=' + BRANCH)
        state = validate_state(json.loads(base64.b64decode(content['content'])))
        return state, content['sha'], True

    def persist(self, plan):
        if not self.token:
            raise ValueError('GH_TOKEN is required only in GitHub Actions to persist state')
        current, sha, exists = self.load()
        if sha != plan['expected_sha'] or exists != plan['branch_existed']:
            raise ValueError('State changed since collection; refusing to overwrite newer cursor')
        if not exists:
            head = self.api('GET', '/git/ref/heads/main')['object']['sha']
            self.api('POST', '/git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': head})
        payload = {'message': 'Record successful ljglobal topic collection', 'branch': BRANCH,
                   'content': base64.b64encode((json.dumps(plan['next_state'], indent=2) + '\n').encode()).decode()}
        if sha:
            payload['sha'] = sha
        return self.api('PUT', '/contents/' + STATE_PATH, payload)


def make_plan(state, items, now, expected_sha=None, existed=False):
    seen = set(state['seen_ids'])
    new_items = [item for item in items if item['id'] not in seen]
    ids = sorted(seen | {i['id'] for i in items})
    if len(ids) > 10000:
        raise ValueError('State reached 10,000 IDs; archive deliberately rather than silently forgetting IDs')
    plan = {'expected_sha': expected_sha, 'branch_existed': existed,
            'next_state': {'version': 1, 'last_success': iso(now), 'seen_ids': ids}}
    return plan, new_items


def write_outputs(out, items, new_items, plan, now):
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [('topics.json', {'source': CATEGORY, 'collected_at': iso(now), 'scope': 'RSS metadata only; not full articles or all historical pages', 'items': items, 'new_items': new_items}), ('prepared-state.json', plan)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    ET.SubElement(channel, 'title').text = '待审选题，不是原创文章'
    ET.SubElement(channel, 'link').text = CATEGORY
    ET.SubElement(channel, 'description').text = '供本地内容工作台导入的短元信息，人工另写原创稿。'
    for item in new_items:
        node = ET.SubElement(channel, 'item')
        for key, target in [('title', 'title'), ('url', 'link'), ('excerpt', 'description'), ('published', 'pubDate')]:
            ET.SubElement(node, target).text = item[key]
    ET.ElementTree(root).write(out / 'topics.rss', encoding='utf-8', xml_declaration=True)


def output_flag(value):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as handle:
            handle.write('collected=' + ('true' if value else 'false') + '\n')


def summary(text):
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write(text + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('collector-output'))
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--local-state', type=Path)
    parser.add_argument('--commit-state', action='store_true')
    args = parser.parse_args(argv)
    if args.commit_state:
        plan = json.loads((args.out / 'prepared-state.json').read_text(encoding='utf-8'))
        validate_state(plan['next_state'])
        GitHubState().persist(plan)
        summary('Collection state persisted to collector-state; website pages were not modified.')
        return 0
    now = now_utc()
    if args.local_state:
        state = validate_state(json.loads(args.local_state.read_text(encoding='utf-8'))) if args.local_state.exists() else initial_state()
        sha, existed = None, False
    else:
        state, sha, existed = GitHubState().load()
    if not due(state, now, args.force):
        output_flag(False)
        summary('Skipped: fewer than 72 hours since the last successful collection. No source requests made.')
        return 0
    items = collect_source(now=now)
    plan, new_items = make_plan(state, items, now, sha, existed)
    write_outputs(args.out, items, new_items, plan, now)
    report = {'status': 'collected', 'observed_at': iso(now), 'feed_items': len(items), 'new_items': len(new_items), 'interval_hours': 72,
              'scope': 'Current source RSS metadata only; no article body or image fetching; no website publication.'}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.local_state:
        args.local_state.parent.mkdir(parents=True, exist_ok=True)
        args.local_state.write_text(json.dumps(plan['next_state'], indent=2) + '\n', encoding='utf-8')
    output_flag(True)
    summary(f"RSS metadata collected: {len(items)} current items, {len(new_items)} new. No article bodies or images downloaded. No website publication.")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, HTTPError, URLError, ET.ParseError, OSError) as exc:
        summary('Collection failed; cursor not advanced: ' + html.escape(str(exc)))
        sys.exit(1)
