#!/usr/bin/env bats
# This file is part of mettmail (https://github.com/spezifisch/mettmail).
# Copyright (c) 2022 spezifisch (https://github.com/spezifisch)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

setup() {
    load "${TEST_HELPER}/bats-support/load.bash"
    load "${TEST_HELPER}/bats-assert/load.bash"
    load "${TEST_HELPER}/bats-file/load.bash"
}

@test "wait until dovecot is up" {
    until nc -z testcot 993; do
        sleep 0.5
    done
}

@test "mail was delivered from a to rxa" {
    assert_dir_exist "/home/rxa/Maildir/new"
    A_MAILS="$(find /home/rxa/Maildir/new -type f | wc -l)"
    [ "${A_MAILS}" -ge 1 ] || fail "rxa didn't get mail"

    MAIL_FILE="$(find /home/rxa/Maildir/new -type f | tail -1)"
    assert_file_contains "${MAIL_FILE}" "^To: a@testcot"
    assert_file_contains "${MAIL_FILE}" "^Subject: test mail"
}

clear_mails() {
    USERNAME="$1"
    MAILDIR="/home/$USERNAME/Maildir"
    assert_dir_exist "$MAILDIR"
    assert_dir_exist "$MAILDIR/cur"
    assert_dir_exist "$MAILDIR/new"
    assert_dir_exist "$MAILDIR/tmp"
    rm -f "$MAILDIR/{cur,new,tmp}/*"
}

@test "deliver mail from rxb to rxc" {
    clear_mails rxb
    clear_mails rxc
}
