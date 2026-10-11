"""Check the non-interactive input path the macOS app uses."""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_mode_cli", ROOT / "macos/cli.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class AppModeTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(cli, "APP_MODE", True))

    def test_secrets_are_read_one_line_at_a_time_from_stdin(self):
        with mock.patch.object(cli.sys, "stdin", io.StringIO(" spaced pass \nsecond\n")):
            self.assertEqual(cli.read_secret("Password: "), " spaced pass ")
            self.assertEqual(cli.read_secret("Password: "), "second")

    def test_missing_secret_line_is_an_error(self):
        for data in ("", "unterminated"):
            with self.subTest(data=data), mock.patch.object(cli.sys, "stdin", io.StringIO(data)):
                with self.assertRaises(cli.ToolError):
                    cli.read_secret("Password: ")

    def test_password_prompt_reads_once_because_the_app_confirms(self):
        with mock.patch.object(cli.sys, "stdin", io.StringIO("hunter2\n")):
            self.assertEqual(cli.prompt_hid_password(), "hunter2")
        with mock.patch.object(cli.sys, "stdin", io.StringIO("\n")):
            with self.assertRaises(cli.ToolError):
                cli.prompt_hid_password()

    def test_choices_take_their_default(self):
        self.assertEqual(cli.ask("Identity [1]: "), "")

    def test_events_are_json_lines(self):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.app_event("reconnect_needed", mode="hid")
        prefix, payload = output.getvalue().strip().split(" ", 1)
        self.assertEqual(prefix, "@tinytouch")
        self.assertEqual(json.loads(payload), {"event": "reconnect_needed", "mode": "hid"})

    def test_sudo_uses_askpass(self):
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            return mock.Mock(returncode=1 if command == ["sudo", "-n", "-v"] else 0)

        with (
            mock.patch.object(cli, "_sudo_session_ready", False),
            mock.patch.object(cli.subprocess, "run", side_effect=run),
            mock.patch.dict(cli.os.environ, {"SUDO_ASKPASS": "/bin/echo"}),
            redirect_stdout(io.StringIO()),
        ):
            cli.authorize_macos()
        self.assertEqual(calls, [["sudo", "-n", "-v"], ["sudo", "-A", "-v"]])

    def test_sudo_without_askpass_fails_instead_of_waiting_for_a_terminal(self):
        with (
            mock.patch.object(cli, "_sudo_session_ready", False),
            mock.patch.object(cli.subprocess, "run", return_value=mock.Mock(returncode=1)),
            mock.patch.dict(cli.os.environ, {}, clear=True),
        ):
            with self.assertRaises(cli.ToolError):
                cli.authorize_macos()


if __name__ == "__main__":
    unittest.main()
