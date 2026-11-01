import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from configure_launcher import configure


class LauncherProfileTests(unittest.TestCase):
    def test_only_four_requested_apps_are_pinned_and_not_hidden(self):
        config = json.loads((ROOT / 'profiles/tcl-55p737/config.json').read_text())
        self.assertEqual(config['dock_apps'], ['com.vk.tv', 'com.google.android.youtube.tv',
                                              'com.happproxy', 'ru.kinopoisk.tv'])
        self.assertFalse(set(config['dock_apps']) & set(config['hidden_apps']))
        self.assertEqual(config['columns'], 4)
        self.assertFalse(config['app_library'])

    def test_disable_list_only_contains_seven_nonessential_entertainment_apps(self):
        names = [line for line in (ROOT / 'profiles/tcl-55p737/apps-to-disable.txt').read_text().splitlines()
                 if line and not line.startswith('#')]
        self.assertEqual(set(names), {'com.netflix.ninja', 'com.amazon.amazonvideo.livingroom',
                                     'au.com.stan.and', 'tv.wuaki.apptv', 'com.google.android.youtube.tvmusic',
                                     'com.google.android.play.games', 'com.google.android.videos'})

    def test_configure_is_idempotent_and_preserves_unrelated_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'config.xml'
            source.write_text('<resources><!-- keep --><string-array name="dock_apps"><item>old</item></string-array>'
                              '<bool name="fill_dock">true</bool><integer name="columns">3</integer>'
                              '<string name="locale" translatable="false">en</string>'
                              '<bool name="untouched">true</bool></resources>')
            config = {'dock_apps': ['com.vk.tv', 'com.happproxy'], 'fill_dock': False, 'columns': 4, 'locale': 'ru'}
            configure(source, config)
            first = source.read_text()
            configure(source, config)
            self.assertEqual(first, source.read_text())
            self.assertIn('<!-- keep -->', first)
            self.assertEqual(ET.fromstring(first).find('bool[@name="untouched"]').text, 'true')

    def test_unknown_resource_does_not_partially_write_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'config.xml'
            original = '<resources><integer name="columns">3</integer></resources>'
            source.write_text(original)
            with self.assertRaises(ValueError):
                configure(source, {'columns': 4, 'misspelled_resource': True})
            self.assertEqual(source.read_text(), original)


if __name__ == '__main__':
    unittest.main()
