#!/usr/bin/env python3
"""Apply a local TV profile to upstream CleanYourTV's supported config.xml only."""
import argparse
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET


def configure(source, profile):
    text = source.read_text(encoding="utf-8")
    for key, value in profile.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError(f"Invalid resource name: {key}")
        if isinstance(value, list):
            tag = "string-array"
            content = "\n" + "".join(f"        <item>{escape(str(item))}</item>\n" for item in value) + "    "
        elif isinstance(value, bool):
            tag, content = "bool", str(value).lower()
        elif isinstance(value, int):
            tag, content = "integer", str(value)
        elif isinstance(value, str):
            tag, content = "string", escape(value)
        else:
            raise ValueError(f"Unsupported resource type: {key}")
        pattern = rf'(<{tag}\b[^>]*\bname="{key}"[^>]*>).*?(</{tag}>)'
        text, count = re.subn(pattern, lambda match: match[1] + content + match[2], text, flags=re.S)
        if count != 1:
            raise ValueError(f"Expected exactly one existing {tag} resource for {key}, found {count}")
    ET.fromstring(text)
    source.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--theme-overlay", action="store_true", help="Apply hidden_apps as a runtime theme to keep the APK small")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    if args.theme_overlay:
        profile = {key: value for key, value in profile.items() if key != "hidden_apps"}
    configure(args.upstream / "launcher/app/src/main/res/values/config.xml",
              profile)
