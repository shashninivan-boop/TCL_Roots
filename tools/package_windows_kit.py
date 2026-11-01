#!/usr/bin/env python3
"""Package the tested upstream launcher and original tools for Windows; no secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = '92fdd142566b8c55a5540a96fcdafb889141f644'
TOOLS = ['tv.py', 'recovery.py', 'b64push.py', 'disable.ps1', 'restore.ps1',
         'requirements.txt', 'adb-closed.py', 'theme.ps1', 'theme_restart.py']


def package(upstream, output):
    revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Unexpected upstream revision; review before packaging')
    apk = upstream / 'launcher/app/build/outputs/apk/release/app-release.apk'
    if not apk.is_file() or apk.stat().st_size >= 589824:
        raise ValueError('Release APK missing or over upstream size limit')
    output.mkdir(parents=True, exist_ok=True)
    kit = output / 'TCL-Clean'
    if kit.exists():
        raise FileExistsError('Refusing to overwrite a previous kit')
    kit.mkdir()
    vendor = kit / 'cleanyourtv'
    (vendor / 'tools').mkdir(parents=True)
    for name in TOOLS:
        shutil.copy2(upstream / 'tools' / name, vendor / 'tools' / name)
    # Include the exact configured launcher sources and their licenses, so the
    # APK can be audited/rebuilt; exclude caches, local SDK paths and keystores.
    shutil.copytree(upstream / 'launcher', vendor / 'launcher',
                    ignore=shutil.ignore_patterns('build', '.gradle', 'local.properties', '*.keystore', '*.jks'))
    target = vendor / 'launcher/app/build/outputs/apk/release/app-release.apk'
    target.parent.mkdir(parents=True)
    shutil.copy2(apk, target)
    for name in ('LICENSE', 'README.md', 'PROMPT.md', 'AGENTS.md'):
        shutil.copy2(upstream / name, vendor / name)
    shutil.copytree(ROOT / 'profiles/tcl-55p737', kit / 'profile')
    shutil.copy2(ROOT / 'windows/RUN.ps1', kit / 'RUN.ps1')
    shutil.copy2(ROOT / 'windows/README-RU.md', kit / 'README-RU.md')
    shutil.copy2(ROOT / 'vendor/cleanyourtv/UPSTREAM.md', kit / 'UPSTREAM.md')
    metadata = {'upstream': 'https://github.com/Gathin23/cleanyourtv', 'revision': revision,
                'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                'apk_size_bytes': apk.stat().st_size,
                'configuration': 'Dock and TV settings in config.xml; full profile/config.json applied with upstream theme.ps1',
                'signing': 'Upstream release build uses signingConfigs.debug. No private key is included.',
                'device_validation': 'Not installed on the physical TV yet.'}
    (kit / 'build.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    archive = output / 'TCL-Clean-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(kit.rglob('*')):
            if path.is_file():
                if path.suffix.lower() in {'.ps1', '.md', '.json', '.txt'}:
                    # Windows PowerShell 5.1 reads non-ASCII scripts as ANSI without a BOM.
                    text = path.read_text(encoding='utf-8-sig')
                    bundle.writestr(str(path.relative_to(output)), b'\xef\xbb\xbf' + text.encode('utf-8'))
                else:
                    bundle.write(path, str(path.relative_to(output)))
    print(archive)
    print('ZIP SHA-256:', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    package(args.upstream, args.output)
