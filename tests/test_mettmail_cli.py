# type: ignore
"""
This file is part of mettmail (https://github.com/spezifisch/mettmail).
Copyright (c) 2022 spezifisch (https://github.com/spezifisch)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from click.testing import CliRunner
from loguru import logger

from mettmail import __version__, mettmail_cli
from mettmail.mettmail_loop import mettmail_loop


def test_version() -> None:
    assert __version__ == "0.2.0"


class TestMettmailCLI(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mock_mettmail_loop = patch("mettmail.mettmail_loop.mettmail_loop", spec_set=mettmail_loop).start()
        self.addCleanup(patch.stopall)

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--help"])
        assert result.exit_code == 0
        assert result.output.startswith("Usage:")

    def test_config_not_found(self):
        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--config", "not-an-existing-file-foo.bar"])
        assert result.exit_code == 1
        assert "No such file" in result.output

    def test_config_incomplete(self):
        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--config", "tests/data/config.incomplete.yaml"])
        assert result.exit_code == 1
        assert "'envelope_recipient' not found" in result.output

    def test_loglevel_trace(self):
        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--trace", "--config", "not-an-existing-file-foo.bar"])
        assert result.exit_code == 1
        assert "level=5" in str(logger)  # hacky but loguru doesn't have a way to request the loglevel

    def test_loglevel_debug(self):
        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--debug", "--config", "not-an-existing-file-foo.bar"])
        assert result.exit_code == 1
        assert "level=10" in str(logger)

    def test_success(self):
        self.mock_mettmail_loop.return_value = True

        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--config", "tests/data/success.yaml"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_failure(self):
        self.mock_mettmail_loop.return_value = False

        runner = CliRunner()
        result = runner.invoke(mettmail_cli.run, ["--config", "tests/data/success.yaml"])
        assert result.exit_code == 1
        assert result.output == ""
