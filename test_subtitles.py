import unittest
from types import SimpleNamespace as NS
import subtitle_core as app

class TimingTests(unittest.TestCase):
    def test_silence_is_not_subtitled(self):
            words = [NS(start=1,end=2,word='Hello'),NS(start=4,end=5,word=' world.')]
            self.assertEqual(app.cues_from_words([NS(words=words)]), [(1,2,'Hello'),(4,5,'world.')])

    def test_overlap_and_invalid_words(self):
            segments = [NS(words=[NS(start=0,end=2,word='A.')]), NS(words=[NS(start=1,end=3,word='B.'),NS(start=4,end=4,word='bad')])]
            self.assertEqual(app.cues_from_words(segments), [(0,2,'A.'),(2,3,'B.')])

    def test_timestamp_carry(self):
            self.assertEqual(app.timestamp(59.9996), '00:01:00,000')
