import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tcl_tv as app


def device():
    props = dict.fromkeys(app.PROPS, "test")
    props.update({"ro.product.manufacturer": "TCL", "ro.product.brand": "TCL",
                  "ro.product.model": "BeyondTV4"})
    return {"properties": props, "features": ["feature:android.software.leanback"],
            "packages": ["package:com.android.settings"], "disabled": []}


class TVTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def args(self, *cmd):
        return app.parser().parse_args(["--tv", "192.168.1.50:5555", *cmd])

    def test_private_endpoint(self):
        self.assertEqual(app.endpoint("192.168.1.50:5555"), "192.168.1.50:5555")

    def test_invalid_or_nonlocal_endpoints(self):
        for value in ("8.8.8.8:5555", "127.0.0.1:5555", "192.168.1.50:0",
                      "192.168.1.50:65536", "192.168.1.50:5555;reboot", "--all", "tv:5555"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                app.endpoint(value)

    def test_store_plan_never_connects(self):
        with patch.object(app, "TV") as tv:
            app.execute(self.args("store", "youtube"))
            tv.assert_not_called()

    def test_apply_requires_physical_model_confirmation(self):
        with patch.object(app, "TV") as tv, self.assertRaises(ValueError):
            app.execute(self.args("store", "vk", "--apply"))
        tv.assert_not_called()

    def test_happ_store_does_not_guess_package(self):
        with patch.object(app, "TV") as tv, self.assertRaises(ValueError):
            app.execute(self.args("store", "happ", "--apply", "--confirm-model", "55P737"))
        tv.assert_not_called()

    def test_foreign_brand_and_non_tv_are_blocked(self):
        info = device()
        app.guard_device(info)
        info["features"] = []
        with self.assertRaises(RuntimeError):
            app.guard_device(info)
        info = device()
        info["properties"]["ro.product.manufacturer"] = "Other"
        info["properties"]["ro.product.brand"] = "Other"
        with self.assertRaises(RuntimeError):
            app.guard_device(info)

    def test_store_takes_snapshot_before_opening_single_page(self):
        events = []
        tv = Mock()
        tv.inspect.return_value = device()
        tv.call.side_effect = lambda *a, **kw: events.append(a) or "Status: ok"
        with patch.object(app, "TV", return_value=tv), patch.object(app, "snapshot", side_effect=lambda *a: events.append("snapshot")):
            app.execute(self.args("store", "kinopoisk", "--apply", "--confirm-model", "55P737"))
        self.assertEqual(events[0], "snapshot")
        self.assertEqual(events[1], ("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
                                    "-d", "market://details?id=ru.kinopoisk.tv", "-p", "com.android.vending"))

    def test_store_android_error_is_not_success(self):
        tv = Mock()
        tv.inspect.return_value = device()
        tv.call.return_value = "Error: Activity not found"
        with patch.object(app, "TV", return_value=tv), patch.object(app, "snapshot"), self.assertRaises(RuntimeError):
            app.execute(self.args("store", "vk", "--apply", "--confirm-model", "55P737"))

    def test_no_changes_if_snapshot_fails(self):
        tv = Mock()
        tv.inspect.return_value = device()
        with patch.object(app, "TV", return_value=tv), patch.object(app, "snapshot", side_effect=OSError("disk full")), self.assertRaises(OSError):
            app.execute(self.args("store", "vk", "--apply", "--confirm-model", "55P737"))
        tv.call.assert_not_called()

    def test_snapshot_is_unique_and_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            first = app.snapshot(device(), folder)
            second = app.snapshot(device(), folder)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text()), device())

    def test_adb_connect_zero_exit_is_not_enough(self):
        with patch.object(app, "run", side_effect=["failed to connect", "offline"]), self.assertRaises(RuntimeError):
            app.TV("192.168.1.50:5555").connect()

    def test_invalid_package_query_is_not_saved_as_inventory(self):
        with patch.object(app.TV, "call", side_effect=["TCL"] * len(app.PROPS) + ["feature:android.software.leanback", "Error: no user", ""]), self.assertRaises(RuntimeError):
            app.TV("192.168.1.50:5555").inspect()

    def test_cli_help_and_plan_need_no_adb_or_tv(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/tcl_tv.py"), "--tv",
                                 "192.168.1.50:5555", "--adb", "missing-adb", "store", "youtube"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("com.google.android.youtube.tv", result.stdout)


class APKTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.apk = Path(self.folder.name) / "tv.apk"
        self.apk.write_bytes(b"test-fixture-not-an-actual-apk")
        self.args = app.parser().parse_args(["--tv", "192.168.1.50:5555", "install-apk", "youtube",
                                            str(self.apk), "--sha256", hashlib.sha256(self.apk.read_bytes()).hexdigest(),
                                            "--cert-sha256", "a" * 64])
        self.badging = "package: name='com.google.android.youtube.tv' versionCode='1'\nleanback-launchable-activity: name='test.Home'"
        self.certs = "Signer #1 certificate SHA-256 digest: " + "a" * 64

    def test_valid_package_and_signature(self):
        with patch.object(app, "run", side_effect=[self.badging, self.certs]):
            self.assertEqual(app.verified_apk(self.args), (self.apk, "com.google.android.youtube.tv"))

    def test_wrong_hash_stops_before_sdk_or_tv(self):
        self.args.sha256 = "b" * 64
        with patch.object(app, "run") as run, self.assertRaises(ValueError):
            app.verified_apk(self.args)
        run.assert_not_called()

    def test_wrong_package_or_non_tv_or_split_refused(self):
        for badging in (self.badging.replace("com.google.android.youtube.tv", "com.unwanted.app"),
                        "package: name='com.google.android.youtube.tv'",
                        self.badging + "\npackage: split='config.en'"):
            with self.subTest(badging=badging), patch.object(app, "run", return_value=badging), self.assertRaises(ValueError):
                app.verified_apk(self.args)

    def test_wrong_or_missing_signer_refused(self):
        for certs in ("", self.certs.replace("a" * 64, "b" * 64)):
            with self.subTest(certs=certs), patch.object(app, "run", side_effect=[self.badging, certs]), self.assertRaises(ValueError):
                app.verified_apk(self.args)

    def test_signature_verification_failure_propagates(self):
        with patch.object(app, "run", side_effect=[self.badging, RuntimeError("DOES NOT VERIFY")]), self.assertRaises(RuntimeError):
            app.verified_apk(self.args)

    def test_apk_plan_never_connects(self):
        with patch.object(app, "run", side_effect=[self.badging, self.certs]), patch.object(app, "TV") as tv, contextlib.redirect_stdout(io.StringIO()):
            app.execute(self.args)
        tv.assert_not_called()

    def test_streamed_install_and_presence_check(self):
        self.args.apply, self.args.confirm_model = True, "55P737"
        tv = Mock()
        tv.inspect.return_value = device()
        tv.call.side_effect = ["Performing Streamed Install\nSuccess", "package:/data/app/base.apk"]
        with patch.object(app, "verified_apk", return_value=(self.apk, "com.google.android.youtube.tv")), patch.object(app, "TV", return_value=tv), patch.object(app, "snapshot"), contextlib.redirect_stdout(io.StringIO()):
            app.execute(self.args)
        self.assertEqual(tv.call.call_args_list[0].args[:2], ("install", "-r"))
        self.assertEqual(tv.call.call_count, 2)

    def test_install_failure_is_not_success_even_if_adb_exits_zero(self):
        self.args.apply, self.args.confirm_model = True, "55P737"
        tv = Mock()
        tv.inspect.return_value = device()
        tv.call.return_value = "Failure [INSTALL_FAILED_NO_MATCHING_ABIS]"
        with patch.object(app, "verified_apk", return_value=(self.apk, "com.google.android.youtube.tv")), patch.object(app, "TV", return_value=tv), patch.object(app, "snapshot"), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            app.execute(self.args)
        self.assertEqual(tv.call.call_count, 1)


class UpstreamCloseTests(unittest.TestCase):
    def test_unknown_reachability_is_never_closed(self):
        spec = importlib.util.spec_from_file_location("close_adb", ROOT / "vendor/cleanyourtv/adb-closed.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for error, expected in ((socket.timeout(), 2), (ConnectionRefusedError(), 0), (OSError("no route"), 2)):
            with self.subTest(error=error), patch.object(sys, "argv", ["adb-closed.py", "192.168.1.50", "5555"]), patch.object(module.socket, "create_connection", side_effect=error), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(), expected)


if __name__ == "__main__":
    unittest.main()
