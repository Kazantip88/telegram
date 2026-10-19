import unittest

from app.telegram_search import SearchStats, main


class TelegramSearchEntrypointTests(unittest.TestCase):
    def test_entrypoint_is_available(self):
        self.assertTrue(callable(main))

    def test_search_stats_defaults(self):
        stats = SearchStats()
        self.assertEqual(stats.sources, 0)
        self.assertEqual(stats.messages, 0)
        self.assertEqual(stats.qualified, 0)
        self.assertEqual(stats.hot, 0)
        self.assertEqual(stats.normal, 0)


if __name__ == "__main__":
    unittest.main()
