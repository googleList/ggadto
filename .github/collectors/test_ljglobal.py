import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('ljglobal.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

RSS = '''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Google Ads测试选题</title><link>https://www.ljglobal.cn/test-topic/?utm_source=test#top</link><description><![CDATA[<p>仅供测试的短摘要</p><script>evil()</script>]]></description><pubDate>Thu, 05 Nov 2026 10:51:00 +0000</pubDate><content:encoded>不可被采集输出的第三方完整正文</content:encoded></item>
<item><title>Google Ads重复网址</title><link>https://www.ljglobal.cn/test-topic/</link><description>重复</description></item>
<item><title>Google AI搜索测试</title><link>https://www.ljglobal.cn/ai-test/</link><description>摘要</description></item>
</channel></rss>'''
NOW = datetime(2026, 11, 6, 3, 17, tzinfo=timezone.utc)


class CollectorTests(unittest.TestCase):
    def test_initial_run_is_due(self):
        self.assertTrue(c.due(c.initial_state(), NOW))

    def test_exact_72_hour_gate_and_cross_month(self):
        previous = datetime(2026, 10, 31, 3, 17, tzinfo=timezone.utc)
        state = {'last_success': c.iso(previous)}
        self.assertFalse(c.due(state, previous + timedelta(hours=71, minutes=59)))
        self.assertTrue(c.due(state, previous + timedelta(hours=72)))

    def test_manual_force_and_future_clock(self):
        self.assertTrue(c.due({'last_success': c.iso(NOW)}, NOW, True))
        with self.assertRaises(ValueError):
            c.due({'last_success': c.iso(NOW + timedelta(days=1))}, NOW)

    def test_extract_metadata_not_body_or_script(self):
        items = c.parse_feed(RSS, c.iso(NOW))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['url'], 'https://www.ljglobal.cn/test-topic/')
        self.assertEqual(items[0]['excerpt'], '仅供测试的短摘要')
        self.assertEqual(items[0]['category'], 'Ads')
        self.assertEqual(items[1]['category'], 'GEO')
        self.assertNotIn('第三方完整正文', json.dumps(items, ensure_ascii=False))
        self.assertNotIn('evil()', json.dumps(items))

    def test_excerpt_is_bounded(self):
        xml = RSS.replace('仅供测试的短摘要', '字' * 900)
        self.assertEqual(len(c.parse_feed(xml, c.iso(NOW))[0]['excerpt']), 350)

    def test_xml_and_empty_source_fail_closed(self):
        for xml in ['<!DOCTYPE rss><rss/>', '<html/>', '<rss><channel/></rss>', '<rss>']:
            with self.assertRaises((ValueError, ET.ParseError)):
                c.parse_feed(xml, c.iso(NOW))

    def test_external_and_non_https_links_rejected(self):
        for url in ['http://www.ljglobal.cn/a/', 'https://evil.example/a/', 'https://www.ljglobal.cn@evil.example/a/', 'file:///a']:
            with self.assertRaises(ValueError):
                c.canonical_url(url)

    def test_deduplication_persists_without_storing_source_urls(self):
        items = c.parse_feed(RSS, c.iso(NOW))
        plan, new = c.make_plan(c.initial_state(), items, NOW)
        self.assertEqual(len(new), 2)
        self.assertNotIn('https://', json.dumps(plan['next_state']))
        second, new = c.make_plan(plan['next_state'], items, NOW + timedelta(days=3))
        self.assertEqual(new, [])
        self.assertEqual(len(second['next_state']['seen_ids']), 2)

    def test_disallow_prevents_feed_request(self):
        calls = []
        def blocked(url):
            calls.append(url)
            return 200, 'User-agent: *\nDisallow: /category/'
        with self.assertRaisesRegex(ValueError, 'disallows'):
            c.collect_source(blocked, NOW)
        self.assertEqual(calls, [c.ROBOTS])

    def test_robots_404_and_public_feed(self):
        def allowed(url):
            return (404, '') if url == c.ROBOTS else (200, RSS)
        self.assertEqual(len(c.collect_source(allowed, NOW)), 2)

    def test_fetch_errors_do_not_make_plan(self):
        state = c.initial_state()
        before = json.dumps(state)
        with self.assertRaises(ValueError):
            c.collect_source(lambda url: (503, ''), NOW)
        self.assertEqual(json.dumps(state), before)

    def test_artifact_rss_is_metadata_only_and_importable(self):
        items = c.parse_feed(RSS, c.iso(NOW))
        plan, new = c.make_plan(c.initial_state(), items, NOW)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            c.write_outputs(out, items, new, plan, NOW)
            text = (out / 'topics.rss').read_text(encoding='utf-8')
            self.assertNotIn('不可被采集输出', text)
            self.assertNotIn('content:encoded', text)
            self.assertEqual(len(ET.fromstring(text).findall('./channel/item')), 2)

    def test_corrupt_state_not_silently_reset(self):
        for state in [{}, {'version': 2, 'seen_ids': []}, {'version': 1, 'seen_ids': ['bad']}]:
            with self.assertRaises(ValueError):
                c.validate_state(state)

    def test_state_save_rejects_changed_remote(self):
        class Conflict(c.GitHubState):
            def load(self):
                return c.initial_state(), 'new-sha', True
            def api(self, *args, **kwargs):
                raise AssertionError('Must not write after a conflict')
        plan = {'expected_sha': 'old-sha', 'branch_existed': True, 'next_state': c.initial_state()}
        with self.assertRaisesRegex(ValueError, 'changed'):
            Conflict('googleList/ggadto', 'test-only-not-a-real-token').persist(plan)

    def test_first_state_save_only_targets_state_branch(self):
        class Fake(c.GitHubState):
            def __init__(self):
                super().__init__('googleList/ggadto', 'test-only-not-a-real-token')
                self.calls = []
            def load(self):
                return c.initial_state(), None, False
            def api(self, method, suffix, payload=None, missing_ok=False):
                self.calls.append((method, suffix, payload))
                return {'object': {'sha': 'base'}} if method == 'GET' else {'ok': True}
        fake = Fake()
        fake.persist({'expected_sha': None, 'branch_existed': False, 'next_state': c.initial_state()})
        self.assertEqual(fake.calls[1][2]['ref'], 'refs/heads/collector-state')
        self.assertEqual(fake.calls[2][2]['branch'], 'collector-state')


if __name__ == '__main__':
    unittest.main()
