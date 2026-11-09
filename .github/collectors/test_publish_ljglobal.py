import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
import ljglobal as C
import publish_ljglobal as P

ROOT = Path(__file__).resolve().parents[2]
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII=')
URL = 'https://www.ljglobal.cn/licensed-example/'
IMAGE = 'https://lingjuimg.com/wp-content/uploads/example.png'
ITEM = {'id': 'a' * 64, 'url': URL, 'title': '授权测试文章', 'category': 'Ads', 'published': 'Thu, 05 Nov 2026 10:51:00 +0000'}
BODY_TEXT = '这是用于离线测试的授权正文段落，不代表任何真实客户案例。' * 15
SOURCE = f'''<!doctype html><html><head><link rel="canonical" href="{URL}"></head><body>
<header>不会采集的导航与联系方式</header><h1>授权测试文章</h1><article class="nnn_article fz16">
<p>{BODY_TEXT}<a href="https://external.example/">保留链接文字但不保留回链</a></p>
<h2 onclick="bad()">原始正文标题</h2><p><img src="{IMAGE}" alt="授权配图" width="650" height="400" onerror="bad()"></p>
<script>evil()</script><iframe src="https://external.example/"></iframe><form>不要带入的表单</form>
<p><a href="https://www.ljglobal.cn/contact/">源站销售联系方式</a>不要冒充本站服务承诺</p>
<p>文章来源：原作者署名模块</p><ul><li>保留原始列表</li></ul>
</article><footer>不采集原站页脚</footer></body></html>'''
DATE = '2026-11-06T04:00:00Z'


class FakeReader:
    def __init__(self, image_failure=False):
        self.calls = []
        self.image_failure = image_failure

    def get(self, url, image=False):
        self.calls.append((url, image))
        if image:
            if self.image_failure:
                raise RuntimeError('Test image download failed')
            return PNG
        return SOURCE.encode()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        for name in ('pages/google-ads-management-fees.html', 'pages/blog-grid.html', 'index.html', 'sitemap.xml', '.github/collectors/ljglobal-rights.json'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def test_parser_offsets_allow_exact_template_edits(self):
        source = '<html>\n<head><script>if (a < b) run()</script></head><body><div class="target">old</div></body></html>'
        node = P.Tree(source).root.find(lambda n: n.has_class('target'))
        result = P.replace_ranges(source, [(node.inner_start, node.inner_end, 'new')])
        self.assertEqual(result, source.replace('>old<', '>new<'))

    def test_full_body_preserved_and_external_code_promo_removed(self):
        reader = FakeReader()
        record, images = P.extract_article(SOURCE, ITEM, reader)
        self.assertIn(BODY_TEXT, C.plain(record['body']))
        self.assertIn('保留原始列表', record['body'])
        self.assertIn('保留链接文字但不保留回链', record['body'])
        for value in ('evil()', 'onclick', 'onerror', '<script', '<iframe', '<form', 'external.example', '源站销售联系方式', '文章来源', '不采集原站页脚'):
            self.assertNotIn(value, record['body'])
        self.assertEqual(next(iter(images.values())), PNG)
        self.assertEqual(record['published_at'], '2026-11-05T10:51:00Z')
        self.assertEqual(len(record['images']), 1)

    def test_raster_magic_and_external_image_host(self):
        self.assertEqual(P.image_extension(PNG), 'png')
        with self.assertRaises(ValueError):
            P.image_extension(b'<svg onload="bad()"/>')
        reader = P.Reader(P.load_config(self.repo))
        with self.assertRaisesRegex(ValueError, 'outside'):
            reader.get('https://evil.example/image.png', image=True)

    def test_original_or_largest_advertised_image_is_used(self):
        attrs = {'src': 'small.png', 'srcset': 'small.png 320w, full.png 2560w, medium.png 1024w'}
        self.assertEqual(P.image_source(attrs), 'full.png')
        attrs['data-orig-file'] = 'camera-original.png'
        self.assertEqual(P.image_source(attrs), 'camera-original.png')

    def test_image_failure_holds_article_without_any_website_files(self):
        files, records, errors, manifest = P.build_stage(self.repo, [ITEM], FakeReader(True), DATE)
        self.assertEqual(files, {})
        self.assertEqual(records, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(manifest['entries'], {})

    def test_missing_article_or_changed_canonical_fails_closed(self):
        for source in (SOURCE.replace('class="nnn_article fz16"', 'class="changed"'), SOURCE.replace(f'href="{URL}"', 'href="https://www.ljglobal.cn/different/"')):
            with self.assertRaises(ValueError):
                P.extract_article(source, ITEM, FakeReader())

    def test_existing_target_never_overwritten(self):
        existing = self.repo / 'pages/licensed-example.html'
        existing.write_text('existing user file', encoding='utf-8')
        reader = FakeReader()
        files, records, errors, _ = P.build_stage(self.repo, [ITEM], reader, DATE)
        self.assertEqual(files, {})
        self.assertEqual(reader.calls, [])
        self.assertEqual(existing.read_text(), 'existing user file')
        self.assertEqual(len(errors), 1)

    def test_no_duplicate_fetch_or_files_after_manifest_has_article(self):
        files, records, errors, _ = P.build_stage(self.repo, [ITEM], FakeReader(), DATE)
        target = self.repo / P.MANIFEST
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[P.MANIFEST])
        reader = FakeReader()
        second, records, errors, _ = P.build_stage(self.repo, [ITEM], reader, DATE)
        self.assertEqual(second, {})
        self.assertEqual(reader.calls, [])
        self.assertEqual(errors, [])

    def test_rendered_page_schema_links_images_and_old_template(self):
        files, records, errors, _ = P.build_stage(self.repo, [ITEM], FakeReader(), DATE)
        self.assertEqual(errors, [])
        page = files['pages/licensed-example.html'].decode()
        tree = P.Tree(page).root
        self.assertEqual(len(tree.all(lambda n: n.tag == 'h1')), 1)
        self.assertIn('https://chaudizhi.com/pages/licensed-example.html', page)
        self.assertNotIn('www.ljglobal.cn', page)
        self.assertNotIn('lingjuimg.com', page)
        article = tree.find(lambda n: n.tag == 'main')
        self.assertNotIn('https://', page[article.start:article.end])
        self.assertIn('datePublished', page)
        self.assertNotIn('"author"', page)
        self.assertIn('../assets/images/imported/ljglobal/', page)
        self.assertIn('id="sticky-header"', page)
        self.assertEqual(files[next(k for k in files if k.endswith('.png'))], PNG)

    def test_listing_home_and_sitemap_preserve_existing_content(self):
        files, _, _, _ = P.build_stage(self.repo, [ITEM], FakeReader(), DATE)
        listing = files['pages/blog-grid.html'].decode()
        self.assertIn('google-ads-management-fees.html', listing)
        self.assertIn('licensed-example.html', listing)
        home = files['index.html'].decode()
        self.assertIn('pages/licensed-example.html', home)
        self.assertIn('谷歌代投与谷歌开户', home)
        xml = ET.fromstring(files['sitemap.xml'])
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        urls = [n.findtext(ns+'loc') for n in xml.findall(ns+'url')]
        self.assertIn('https://chaudizhi.com/pages/google-ads.html', urls)
        self.assertEqual(urls.count('https://chaudizhi.com/pages/licensed-example.html'), 1)

    def test_home_keeps_exactly_four_latest_imported_articles(self):
        _, records, _, _ = P.build_stage(self.repo, [ITEM], FakeReader(), DATE)
        entries = []
        for i in range(7):
            r = copy.deepcopy(records[0])
            r['file'] = f'pages/example-{i}.html'
            r['published_at'] = f'2026-11-0{i+1}T10:00:00Z'
            entries.append(r)
        result = P.update_home((self.repo/'index.html').read_text(encoding='utf-8'), entries)
        carousel = P.Tree(result).root.find(lambda n: n.has_class('blog-list-3'))
        self.assertEqual(len(carousel.all(lambda n: n.has_class('single-blog-box'))), 4)
        self.assertIn('pages/example-6.html', result)
        self.assertNotIn('pages/example-0.html', result)

    def test_home_preserves_newer_original_article_without_duplicates(self):
        original = {'title': 'Original guide', 'description': 'Original', 'category': 'Ads',
                    'published_at': '2026-11-09', 'file': 'pages/original.html', 'images': []}
        imported = dict(original, title='Imported guide', published_at='2026-11-05T10:00:00Z',
                        file='pages/imported.html', imported_at=DATE)
        source = '<div class="blog-list-3">' + P.card(original, True) + P.card(imported, True) + '</div>'
        result = P.update_home(source, [imported])
        carousel = P.Tree(result).root.find(lambda n: n.has_class('blog-list-3'))
        self.assertEqual(len(carousel.all(lambda n: n.has_class('single-blog-box'))), 2)
        self.assertLess(result.index('Original guide'), result.index('Imported guide'))
        self.assertEqual(len(carousel.all(lambda n: n.tag == 'h3' and 'Imported guide' in n.text())), 1)

    def test_no_source_body_content_in_manifest(self):
        files, _, _, _ = P.build_stage(self.repo, [ITEM], FakeReader(), DATE)
        manifest = json.loads(files[P.MANIFEST])
        self.assertEqual(manifest['entries'][ITEM['id']]['source_url'], URL)
        self.assertNotIn('body', manifest['entries'][ITEM['id']])

    def test_authorization_disable_switch(self):
        target = self.repo / '.github/collectors/ljglobal-rights.json'
        config = json.loads(target.read_text(encoding='utf-8'))
        config['enabled'] = False
        target.write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'disabled'):
            P.load_config(self.repo)

    def test_concurrent_main_changes_reject_before_creating_blobs(self):
        class API:
            def __init__(self): self.calls = []
            def api(self, method, endpoint, payload=None):
                self.calls.append(method)
                return {'object': {'sha': 'new-main'}}
        api = API()
        with patch.object(P.subprocess, 'run', return_value=types.SimpleNamespace(stdout='old-main')):
            with self.assertRaisesRegex(ValueError, 'Main changed'):
                P.publish_commit(api, self.repo, {'pages/example.html': b'test'})
        self.assertEqual(api.calls, ['GET'])

    def test_partial_failure_does_not_advance_cursor(self):
        class API:
            def load(self): return C.initial_state(), 'expected', True
            def persist(self, plan): raise AssertionError('Must not persist on partial failure')
        with patch.object(C, 'GitHubState', return_value=API()), patch.dict(P.os.environ, {'EXPECTED_STATE_SHA': 'expected', 'HAS_FAILURES': 'true'}):
            with self.assertRaisesRegex(ValueError, 'held'):
                P.finalize(self.repo)


if __name__ == '__main__':
    unittest.main()
