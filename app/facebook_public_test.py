import unittest

from app.facebook_public import _direct_post, _search_links


class FacebookPublicParserTests(unittest.TestCase):
    def test_parses_bing_rss_facebook_post(self):
        payload = b'''<?xml version="1.0"?><rss><channel><item><title>Max Mustermann | Facebook</title><link>https://www.facebook.com/groups/test/posts/123456/</link><description>Ich habe Geld verloren und kann es nicht zuruckbekommen.</description></item></channel></rss>'''
        items = _search_links(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://www.facebook.com/groups/test/posts/123456/")
        self.assertTrue(_direct_post(items[0]["link"]))

    def test_parses_google_style_redirect(self):
        payload = b'''<html><a href="/url?q=https%3A%2F%2Fwww.facebook.com%2Fgroups%2Ftest%2Fposts%2F777%2F">John Doe | Facebook</a></html>'''
        items = _search_links(payload)
        self.assertEqual(len(items), 1)
        self.assertIn("facebook.com/groups/test/posts/777", items[0]["link"])

    def test_non_post_facebook_page_is_not_direct_post(self):
        self.assertFalse(_direct_post("https://www.facebook.com/somepage"))


if __name__ == "__main__":
    unittest.main()
