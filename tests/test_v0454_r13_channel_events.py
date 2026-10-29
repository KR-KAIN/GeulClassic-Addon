"""Channel fallback must respect real arrivals observed in the user's video."""
import json
from pathlib import Path
import unittest

from kain_maple_translator.channel_guard import ChannelGuard


DATA = json.loads((Path(__file__).parent/'fixtures/r13/channel-bounces.json').read_text(encoding='utf-8'))


class VideoChannelEventTests(unittest.TestCase):
    def test_same_event_classifier_bounces_remain_suppressed(self):
        self.assertGreaterEqual(len(DATA['pairs']), 10)
        for pair in DATA['pairs']:
            before, after = pair['before'], pair['after']
            if before['row'].get('_visual_event_id') != after['row'].get('_visual_event_id'):
                continue
            with self.subTest(second=after['second']):
                guard = ChannelGuard()
                self.assertTrue(guard.accept(before['row'], before['second']))
                self.assertFalse(guard.accept(after['row'], after['second']))

    def test_video_reposts_survive_classifier_change(self):
        before, after = DATA['reposts']
        self.assertEqual(before['row']['body'], after['row']['body'])
        self.assertNotEqual(before['row']['_visual_event_id'], after['row']['_visual_event_id'])
        guard = ChannelGuard()
        self.assertTrue(guard.accept(before['row'], before['second']))
        # Both source posts really coexist in one recorded frame. Exercise
        # the classification drift observed elsewhere in that same recording.
        drifted = {**after['row'], 'kind': 'unknown'}
        self.assertTrue(guard.accept(drifted, after['second']))

    def test_legacy_rows_without_ids_keep_existing_guard(self):
        pair = DATA['pairs'][0]
        before = {k:v for k,v in pair['before']['row'].items() if k!='_visual_event_id'}
        after = {k:v for k,v in pair['after']['row'].items() if k!='_visual_event_id'}
        guard = ChannelGuard()
        self.assertTrue(guard.accept(before, pair['before']['second']))
        self.assertFalse(guard.accept(after, pair['after']['second']))
