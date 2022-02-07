#!/usr/bin/env bats
# This file is part of mettmail (https://github.com/spezifisch/mettmail).
# Copyright (c) 2022 spezifisch (https://github.com/spezifisch)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

setup() {
    load "${TEST_HELPER}/bats-support/load.bash"
    load "${TEST_HELPER}/bats-assert/load.bash"
    load "${TEST_HELPER}/bats-file/load.bash"

    cd "${BATS_TEST_DIRNAME}"
}

@test "wait until dovecot is up" {
    IMAP_HOST="testcot"
    IMAP_PORT=993
    until nc -z "${IMAP_HOST}" "${IMAP_PORT}"; do
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
    rm -f "$MAILDIR"/{cur,new,tmp}/*
}

# send mail using LMTP
send_mail() {
    FILE="$1"
    assert_file_exist "$FILE"

    ENV_FROM="${2:-bats-test@spezifisch.github.io}"
    ENV_TO="${3:-rxb}"
    LMTP_HOST="${4:-testcot}"
    LMTP_PORT="${5:-24}"

    (
        # first part is LHLO and mail envelope
        sed -e "s/ENV_FROM/${ENV_FROM}/g" -e "s/ENV_TO/${ENV_TO}/g" mails/LMTP_HEAD
        # second part is the mail itself and last part is the EOF marker and quit command
        cat "$FILE" mails/LMTP_TAIL
    ) | while read; do
        # throttle line sending speed, see https://stackoverflow.com/a/46968824
        sleep .05
        echo "$REPLY"
    done | nc "${LMTP_HOST}" "${LMTP_PORT}"
}

@test "deliver mail from rxb to rxc" {
    clear_mails rxb
    clear_mails rxc

    send_mail mails/simple.eml
    sleep 5 # testcot receives the mail, mettmail receives and delivers it...
    MAIL_FILE="$(find /home/rxc/Maildir/new -type f | tail -1)"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxb$"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxc$"
    assert_file_contains "${MAIL_FILE}" "^From: spezifisch "
    assert_file_contains "${MAIL_FILE}" "^To: spezifisch/mettmail "
    assert_file_contains "${MAIL_FILE}" "^Finished: 2022-01-13 21:37:23 UTC"
}

@test "unicode test plain (unencoded)" {
    clear_mails rxb
    clear_mails rxc

    # generated with https://gist.github.com/ymirpl/1052094/ (header_enc = body_enc = None)
    send_mail mails/unicode-plain.eml
    sleep 5
    MAIL_FILE="$(find /home/rxc/Maildir/new -type f | tail -1)"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxb$"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxc$"
    assert_file_contains "${MAIL_FILE}" '^From: "⌘unicode guy⌘" <one@example.com>'
    assert_file_contains "${MAIL_FILE}" '^To: "🎃jack" <two@example.com>'
    assert_file_contains "${MAIL_FILE}" "^Test⏎"
}

@test "unicode test quoted-printable" {
    clear_mails rxb
    clear_mails rxc

    # generated with https://gist.github.com/ymirpl/1052094/
    send_mail mails/unicode-qp.eml
    sleep 5
    MAIL_FILE="$(find /home/rxc/Maildir/new -type f | tail -1)"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxb$"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxc$"
    assert_file_contains "${MAIL_FILE}" '^From: "=?utf-8?q?=E2=8C=98unicode_guy=E2=8C=98?=" <one@example.com>'
    assert_file_contains "${MAIL_FILE}" "^Test=E2=8F=8E"
}

@test "unicode test base64" {
    clear_mails rxb
    clear_mails rxc

    # generated with https://gist.github.com/ymirpl/1052094/ (default Charset)
    send_mail mails/unicode-base64.eml
    sleep 5
    MAIL_FILE="$(find /home/rxc/Maildir/new -type f | tail -1)"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxb$"
    assert_file_contains "${MAIL_FILE}" "^Delivered-To: rxc$"
    assert_file_contains "${MAIL_FILE}" '^From: "=?utf-8?b?4oyYdW5pY29kZSBndXnijJg=?=" <one@example.com>'
    assert_file_contains "${MAIL_FILE}" "^VW5pY29kZeKPjgpUZXN04o+O"
}
