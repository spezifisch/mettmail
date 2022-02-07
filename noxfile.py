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

import nox


@nox.session(python=["3.8", "3.9", "3.10"], reuse_venv=True)
def tests(session):
    session.install("poetry")
    session.run("poetry", "install")
    session.run("coverage", "run", "-m", "pytest")
    session.run("coverage", "report")


@nox.session(python=["3.10"], reuse_venv=True)
def lint(session):
    session.install("poetry")
    session.run("poetry", "install", "--no-root")
    session.run("flake8", "--max-line-length=120", "mettmail", "tests")
    session.run("mypy", "--strict", ".")
    session.run("black", "--check", "mettmail", "tests")
