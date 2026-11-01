#!/usr/bin/env python3
"""Local ADB assistant for a TCL 55P737. Python 3.10+, Google platform-tools.

No firmware writes, rooting, package removal, launcher replacement or downloads.
All device changes require --apply and --confirm-model 55P737.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


APPS = {
    "youtube": ("YouTube для Android TV", "com.google.android.youtube.tv"),
    "vk": ("VK Видео для Android TV", "com.vk.tv"),
    "kinopoisk": ("Кинопоиск для Android TV", "ru.kinopoisk.tv"),
    # Do not guess a package or download from an unofficial APK catalogue.
    "happ": ("Happ — https://www.happ.su/main/ru", None),
}
PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")
PROPS = ("ro.product.manufacturer", "ro.product.brand", "ro.product.model",
         "ro.build.version.release", "ro.build.version.sdk", "ro.build.fingerprint",
         "ro.product.cpu.abilist")


def endpoint(value):
    """Only an explicit RFC1918 address and port: never scan the network."""
    try:
        host, port = value.rsplit(":", 1)
        address = ipaddress.IPv4Address(host)
        if not any(address in ipaddress.ip_network(net) for net in
                   ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            raise ValueError
        if not 1 <= int(port) <= 65535:
            raise ValueError
        return f"{address}:{int(port)}"
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Нужен локальный IPv4:порт, например 192.168.1.50:5555") from exc


def run(argv, timeout=45):
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


class TV:
    def __init__(self, target, adb="adb"):
        self.target, self.adb = target, adb

    def call(self, *args, timeout=45):
        return run([self.adb, "-s", self.target, *args], timeout=timeout)

    def connect(self):
        message = run([self.adb, "connect", self.target])
        # adb connect sometimes exits zero even if it could not connect.
        if self.call("get-state") != "device":
            raise RuntimeError(f"ADB не авторизован: {message}. Подтвердите доступ на ТВ.")

    def inspect(self):
        props = {key: self.call("shell", "getprop", key) for key in PROPS}
        features = self.call("shell", "pm", "list", "features").splitlines()
        packages = self.call("shell", "pm", "list", "packages", "--user", "0").splitlines()
        disabled = self.call("shell", "pm", "list", "packages", "-d", "--user", "0").splitlines()
        if not packages or any(not line.startswith("package:") for line in packages):
            raise RuntimeError("Не удалось прочитать список пакетов пользователя 0.")
        return {"time_utc": datetime.now(timezone.utc).isoformat(), "properties": props,
                "features": features, "packages": sorted(packages), "disabled": sorted(disabled)}


def guard_device(info):
    props = info["properties"]
    maker = " ".join(props[key] for key in ("ro.product.manufacturer", "ro.product.brand")).lower()
    if "tcl" not in maker.split():
        raise RuntimeError("Устройство не сообщает бренд/производителя TCL; изменения запрещены.")
    if not {"feature:android.software.leanback", "feature:android.hardware.type.television"}.intersection(info["features"]):
        raise RuntimeError("Устройство не сообщает поддержку Android TV; изменения запрещены.")


def snapshot(info, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves previous records even with concurrent runs.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="tv-", suffix=".json",
                                     dir=directory, delete=False) as file:
        json.dump(info, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Снимок состояния: {file.name} (это не резервная копия прошивки или данных приложений)")
    return Path(file.name)


def verified_apk(args):
    """Require both a known package and publisher certificate, not just a filename."""
    path = Path(args.apk).resolve(strict=True)
    if path.suffix.lower() != ".apk" or not path.is_file():
        raise ValueError("Нужен один APK; split APK/XAPK/APKS не поддерживаются.")
    for value in (args.sha256, args.cert_sha256):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("SHA-256 должен содержать 64 шестнадцатеричных символа.")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest.lower() != args.sha256.lower():
        raise ValueError("Контрольная сумма APK не совпала.")
    expected = APPS[args.app][1]
    if args.app == "happ":
        expected = args.package
        if not expected or not PACKAGE.fullmatch(expected):
            raise ValueError("Для Happ укажите --package из проверенного официального APK.")
    badging = run([args.aapt, "dump", "badging", str(path)])
    match = re.search(r"^package: name='([^']+)'", badging, re.MULTILINE)
    if not match or match[1] != expected:
        raise ValueError("Идентификатор APK не совпадает с выбранным приложением.")
    if "split='" in badging:
        raise ValueError("Отдельный split APK не поддерживается.")
    if not re.search(r"^leanback-launchable-activity:", badging, re.MULTILINE):
        raise ValueError("APK не объявляет запуск с пульта Android TV.")
    signatures = run([args.apksigner, "verify", "--verbose", "--print-certs", str(path)])
    certificates = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$",
                              signatures, re.MULTILINE)
    if not certificates or {v.lower() for v in certificates} != {args.cert_sha256.lower()}:
        raise ValueError("Сертификат подписанта не совпадает с ожидаемым сертификатом издателя.")
    return path, expected


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tv", required=True, type=endpoint, help="IP:порт из настроек ТВ")
    p.add_argument("--adb", default="adb", help="Путь к adb из Google platform-tools")
    p.add_argument("--backups", default="backups")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="Прочитать модель, версии, ABI и список приложений")
    store = sub.add_parser("store", help="Открыть страницу выбранного приложения Google Play")
    store.add_argument("app", choices=APPS)
    apk = sub.add_parser("install-apk", help="Проверить и установить локальный официальный TV APK")
    apk.add_argument("app", choices=APPS)
    apk.add_argument("apk")
    apk.add_argument("--sha256", required=True)
    apk.add_argument("--cert-sha256", required=True, help="SHA-256 сертификата официального издателя")
    apk.add_argument("--package", help="Точный package ID Happ из проверенного источника")
    apk.add_argument("--aapt", default="aapt")
    apk.add_argument("--apksigner", default="apksigner")
    for cmd in (store, apk):
        cmd.add_argument("--apply", action="store_true", help="Без этого флага только план")
        cmd.add_argument("--confirm-model", choices=["55P737"], help="Модель с наклейки телевизора")
    return p


def execute(args):
    apk = package = None
    if args.command == "store":
        package = APPS[args.app][1]
        if package is None:
            raise ValueError("Happ: официальный package ID пока не подтверждён. Используйте официальный TV APK.")
        print(f"Google Play: {APPS[args.app][0]} ({package}). Установку подтверждает пользователь на ТВ.")
    elif args.command == "install-apk":
        apk, package = verified_apk(args)
        print(f"APK проверен: {package}. План: adb install -r (без понижения версии и автoвыдачи разрешений).")
    if args.command != "inspect":
        if not args.apply:
            print("Только план: соединение с ТВ не открывалось. Для выполнения: --apply --confirm-model 55P737")
            return
        if args.confirm_model != "55P737":
            raise ValueError("Сверьте модель на наклейке и добавьте --confirm-model 55P737.")
    tv = TV(args.tv, args.adb)
    tv.connect()
    before = tv.inspect()
    if args.command != "inspect":
        guard_device(before)
    snapshot(before, args.backups)
    if args.command == "inspect":
        print(json.dumps(before, ensure_ascii=False, indent=2))
    elif args.command == "store":
        output = tv.call("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
                         "-d", f"market://details?id={package}", "-p", "com.android.vending")
        if "Status: ok" not in output or "Error" in output:
            raise RuntimeError(f"Google Play не открылся: {output}")
        print("Страница открыта. Проверьте название/издателя, установите приложение пультом и запустите его.")
    else:
        output = tv.call("install", "-r", str(apk), timeout=180)
        if not output.splitlines() or output.splitlines()[-1].strip() != "Success":
            raise RuntimeError(f"Установка не подтверждена: {output}")
        installed = tv.call("shell", "pm", "path", "--user", "0", package)
        if not installed.startswith("package:"):
            raise RuntimeError("ADB сообщил Success, но пакет не найден для пользователя 0.")
        print("Пакет установлен. Проверьте запуск пультом; работу сервиса проверяет пользователь.")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        execute(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
