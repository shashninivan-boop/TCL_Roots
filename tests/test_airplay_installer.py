"""PowerShell integration checks against fake ADB and a locally verified release APK."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('PWSH_BIN') or shutil.which('pwsh')
APK = os.environ.get('AIRPLAY_TEST_APK')
FAKE = '''import json,os,sys
args=sys.argv[1:]
with open(os.environ['TCL_TEST_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
args=args[2:] if args[:1]==['-s'] else args
if args==['get-state']: print('device')
elif args[:3]==['shell','getprop','ro.build.version.sdk']: print('30')
elif args[:3]==['shell','getprop','ro.product.cpu.abilist']: print('armeabi-v7a,armeabi')
elif args[:1]==['install']:
 print('Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]' if os.environ.get('TCL_TEST_FAIL_INSTALL') else 'Performing Streamed Install\\nSuccess')
elif args[:3]==['shell','pm','path']: print('package:/data/app/receiver/base.apk')
elif args[:3]==['shell','am','start']: print('Status: ok')
elif args[:3]==['shell','am','broadcast']: print('Broadcast completed: result=-1, data="setting=true"')
elif args[:3]==['shell','cmd','package']: print('com.gathin.tvhome/.MainActivity')
else: print('connected')
'''


@unittest.skipUnless(PWSH and os.name == 'posix', 'Requires PowerShell on POSIX for fake ADB')
class AirPlayInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='airplay test space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / 'windows/INSTALL-AIRPLAY.ps1', self.root / 'INSTALL-AIRPLAY.ps1')
        self.apk = self.root / 'airplay-download/airplay-v0.0.36.apk'
        self.apk.parent.mkdir()
        self.adb = self.root / 'adb.exe'
        self.adb.write_text('#!' + sys.executable + '\n' + FAKE)
        self.adb.chmod(0o755)
        self.log = self.root / 'commands.jsonl'

    def run_installer(self, install=False, fail_install=False):
        child_env = os.environ.copy()
        child_env.update({'TCL_TEST_LOG': str(self.log), 'XDG_DATA_HOME': str(self.root / 'data'),
                          'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_CACHE_HOME': str(self.root / 'cache')})
        if fail_install:
            child_env['TCL_TEST_FAIL_INSTALL'] = '1'
        cmd = [PWSH, '-NoLogo', '-NoProfile', '-File', str(self.root / 'INSTALL-AIRPLAY.ps1'),
               '-TvHost', '192.168.1.50', '-AdbPath', str(self.adb)]
        if install:
            cmd.append('-Install')
        result = subprocess.run(cmd, env=child_env, capture_output=True, text=True, timeout=30)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def official_apk(self):
        if not APK or not Path(APK).is_file():
            self.skipTest('Set AIRPLAY_TEST_APK to the verified official v0.0.36 APK for offline checks')
        shutil.copy2(APK, self.apk)

    def test_checksum_failure_never_contacts_tv(self):
        self.apk.write_bytes(b'corrupted download')
        result, calls = self.run_installer(install=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertEqual(calls, [])

    def test_download_only_never_contacts_tv(self):
        self.official_apk()
        result, calls = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_install_failure_never_reconfigures_or_uninstalls(self):
        self.official_apk()
        result, calls = self.run_installer(install=True, fail_install=True)
        self.assertNotEqual(result.returncode, 0)
        commands = json.dumps(calls)
        self.assertNotIn('broadcast', commands)
        self.assertNotIn('uninstall', commands)
        self.assertNotIn('set-home-activity', commands)

    def test_configures_only_receiver_and_preserves_home(self):
        self.official_apk()
        result, calls = self.run_installer(install=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = json.dumps(calls)
        self.assertNotIn('set-home-activity', commands)
        self.assertNotIn('disable-user', commands)
        broadcasts = [call for call in calls if 'broadcast' in call]
        self.assertEqual(len(broadcasts), 7)
        self.assertTrue(all('io.github.jqssun.airplay/.SettingsReceiver' in call for call in broadcasts))
        self.assertIn('TCL-AirPlay', result.stdout)


if __name__ == '__main__':
    unittest.main()
