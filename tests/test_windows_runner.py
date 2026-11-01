"""Exercise the PowerShell wrapper on POSIX using fake native programs, never a TV."""
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
FAKE = '''import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['TCL_TEST_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
if args[:2]==['-m','pip']: sys.exit(0)
if args[:1]==['-I']:
    if args[1]=='-c': sys.exit(1) # lost recovery record must block restore
    command=args[2] if len(args)>2 else ''
    if command=='pm list packages --user 0':
        print('package:com.vk.tv\\npackage:com.google.android.youtube.tv\\npackage:com.happproxy\\npackage:ru.kinopoisk.tv')
    elif 'resolve-activity' in command: print('com.google.android.apps.tv.launcherx/.HomeActivity')
    elif command=='getprop': print('[ro.product.manufacturer]: [TCL]')
    else: print('test response')
elif args[-1:] == ['get-state']: print('device')
else: print('connected')
'''


@unittest.skipUnless(PWSH and os.name == 'posix', 'Requires PowerShell on POSIX for fake native executables')
class WindowsRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tcl wrapper space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / 'windows/RUN.ps1', self.root / 'RUN.ps1')
        shutil.copytree(ROOT / 'profiles/tcl-55p737', self.root / 'profile')
        py = self.root / 'cleanyourtv/tools/venv/Scripts/python.exe'
        py.parent.mkdir(parents=True)
        self.adb = self.root / 'adb.exe'
        for file in (py, self.adb):
            file.write_text('#!' + sys.executable + '\n' + FAKE)
            file.chmod(0o755)
        self.log = self.root / 'commands.jsonl'

    def run_mode(self, mode):
        child_env = os.environ.copy()
        child_env.update({'TCL_TEST_LOG': str(self.log), 'XDG_DATA_HOME': str(self.root / 'data'),
                          'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_CACHE_HOME': str(self.root / 'cache')})
        result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(self.root / 'RUN.ps1'),
                                 '-TvHost', '192.168.1.50', '-AdbPath', str(self.adb), '-Mode', mode],
                                env=child_env, capture_output=True, text=True, timeout=30)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, commands

    def test_inspect_saves_local_state_and_audit_without_writes(self):
        result, commands = self.run_mode('Inspect')
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((self.root / 'backup').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / 'settings-secure.txt').is_file())
        self.assertIn('PACKAGE: com.tcl.bi', (backups[0] / 'advertising-candidates.txt').read_text(encoding='utf-8-sig'))
        flattened = json.dumps(commands)
        self.assertNotIn('disable-user', flattened)
        self.assertNotIn('set-home-activity', flattened)

    def test_cleanup_refuses_if_new_launcher_does_not_own_home(self):
        result, commands = self.run_mode('Clean')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not the default Home', result.stderr)
        self.assertNotIn('disable-user', json.dumps(commands))

    def test_restore_refuses_lost_record(self):
        result, commands = self.run_mode('Restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('pm enable', json.dumps(commands))


if __name__ == '__main__':
    unittest.main()
