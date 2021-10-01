#!/usr/bin/env python3.8
"""Reconnects to the first character of the tibia client."""

import os
import argparse
import time
import sys

from tibia_terminator.schemas.credentials_schema import (CredentialsSchema, Credential)
from tibia_terminator.reader.window_utils import (get_tibia_wid, focus_tibia,
                                                  send_key, send_text,
                                                  left_click,
                                                  get_pixel_color_slow, Key)

parser = argparse.ArgumentParser(description='Tibia reconnector')
parser.add_argument('pid', help='The PID of Tibia.')
parser.add_argument('--credentials_user',
                    help='User to login from list of credentials.',
                    type=str)
parser.add_argument('--credentials_path',
                    help='Path to credentials configuration file.',
                    type=str)
parser.add_argument('--check_if_ingame',
                    help='Exits with code 0 if the charcacter is in-game',
                    action='store_true')
parser.add_argument('--login',
                    help='Logs in the first character in the list.',
                    action='store_true')
parser.add_argument('--debug_level',
                    help='Verbosity level of debug message. (Default: 0)',
                    type=int,
                    default=0)
parser.add_argument('--max_wait',
                    help='Maximum amount of time to keep retrying in minutes',
                    type=int,
                    dest='max_wait_minutes',
                    default=120)

DEBUG_LEVEL = 0
SCREEN_SPECS = {"logged_out": ["84a3b7", "a9684c", "4f3d55", "b85955"]}
SCREEN_COORDS = [(1132, 316), (1531, 713), (480, 310), (482, 546)]
CREDENTIALS_SCHEMA = CredentialsSchema()
LOGGED_IN_EXIT_STATUS = 0
LOGGED_OUT_EXIT_STATUS = 2
FAILURE_EXIT_STATUS = 1
# Login screen coordinates
# TODO: Make these configurable through JSON
EMAIL_FIELD_XY = (989, 477)
PASSWD_FIELD_XY = (973, 506)
LOGIN_BTN_XY =  (1040, 610)
CHAR_LIST_OK_BTN_XY = (1226, 725)


def debug(msg, debug_level=0):
    if DEBUG_LEVEL <= debug_level:
        print(msg)


class IntroScreenReader():
    def is_screen(self, tibia_wid, name):
        def fn(xy):
            return get_pixel_color_slow(tibia_wid, xy[0], xy[1])

        pixels = list(map(fn, SCREEN_COORDS))
        match = True
        for i in range(0, 4):
            if pixels[i] != SCREEN_SPECS[name][i]:
                debug(
                    '%s (%s) is not equal to %s' %
                    (pixels[i], i, SCREEN_SPECS[name][i]), 1)
                match = False
        return match

    def is_logged_out_screen(self, tibia_wid):
        return self.is_screen(tibia_wid, 'logged_out')


def check_ingame(tibia_wid):
    reader = IntroScreenReader()
    return not reader.is_logged_out_screen(tibia_wid)


def close_dialogs(tibia_wid):
    # Menus are closed by either of these 2 keys.
    for i in range(5):
        send_key(tibia_wid, Key.ESCAPE)
        time.sleep(0.5)
        send_key(tibia_wid, Key.ENTER)
        time.sleep(0.5)
        send_key(tibia_wid, Key.SPACE)
        time.sleep(0.25)
        send_key(tibia_wid, Key.BACKSPACE)
        time.sleep(0.25)

def clear_text_field(tibia_wid, x: int, y: int):
    # focus field
    left_click(tibia_wid, x, y)
    time.sleep(0.1)
    # clear text
    send_key(tibia_wid, Key.HOME)
    time.sleep(0.25)
    send_key(tibia_wid, f"{Key.SHIFT}+{Key.END}")
    time.sleep(0.25)
    send_key(tibia_wid, Key.BACKSPACE)
    time.sleep(0.25)


def overwrite_text_field(tibia_wid, x: int, y: int, new_text: str):
    clear_text_field(tibia_wid, x, y)
    send_text(tibia_wid, new_text)
    time.sleep(0.1)


def login(tibia_wid, credential: Credential):
    # Focus tibia window
    focus_tibia(tibia_wid)
    time.sleep(0.5)
    close_dialogs(tibia_wid)
    time.sleep(0.25)
    # fill-in email field
    overwrite_text_field(
        tibia_wid, EMAIL_FIELD_XY[0], EMAIL_FIELD_XY[1], credential.user
    )
    # fill-in password
    overwrite_text_field(
        tibia_wid, PASSWD_FIELD_XY[0], PASSWD_FIELD_XY[1], credential.password
    )
    # Click [Login] button
    left_click(tibia_wid, LOGIN_BTN_XY[0], LOGIN_BTN_XY[1])
    time.sleep(5)
    #   - Focus should be on the 1st char on the list.
    # Click [OK] in char menu
    left_click(tibia_wid, CHAR_LIST_OK_BTN_XY[0], CHAR_LIST_OK_BTN_XY[1])
    #   - Spin-wait for 30 seconds waiting for character to be in-game
    for _ in range(1, 30):
        if check_ingame(tibia_wid):
            return True
        time.sleep(1)
    # 8a. If after 30 seconds char is not in-game, return False
    return False


def acquire_lock():
    open('./.tibia_reconnector.lock', 'a').close()


def release_lock():
    os.remove('./.tibia_reconnector.lock')


def wait_for_lock():
    if not os.path.exists('.tibia_reconnector.lock'):
        return True

    print('Another Tibia account is reconnecting, waiting.')
    max_wait_retry_secs = 60 * 64
    wait_retry_secs = 60
    while wait_retry_secs <= max_wait_retry_secs:
        locked = os.path.exists('.tibia_reconnector.lock')
        if locked:
            print('Still locked.')
            print('Waiting %s seconds before retrying.' % wait_retry_secs)
            time.sleep(wait_retry_secs)
        else:
            return True
        wait_retry_secs *= 2

    return False


def handle_login(tibia_wid, credentials, max_wait_minutes):
    max_wait_secs = max_wait_minutes * 60
    wait_retry_secs = 60
    total_wait_secs = 0
    while total_wait_secs + wait_retry_secs <= max_wait_secs:
        if check_ingame(tibia_wid):
            print('The character is already in-game.', file=sys.stderr)
            sys.exit(LOGGED_IN_EXIT_STATUS)

        if not wait_for_lock():
            raise Exception('Timed out waiting for lock to be released.')
        else:
            print('Acquiring lock.')
            acquire_lock()

        try:
            if login(tibia_wid, credentials):
                print('Login succeeded.')
                sys.exit(LOGGED_IN_EXIT_STATUS)
            else:
                print('Login failed.')
        finally:
            print('Releasing lock.')
            release_lock()
        print('Waiting %s seconds before retrying.' % wait_retry_secs)
        time.sleep(wait_retry_secs)
        total_wait_secs += wait_retry_secs
        wait_retry_secs *= 2
    sys.exit(LOGGED_OUT_EXIT_STATUS)


def handle_check(tibia_wid):
    """Handles the case where the user only wants to check if the character is
    in-game."""
    if check_ingame(tibia_wid):
        sys.exit(LOGGED_IN_EXIT_STATUS)
    else:
        sys.exit(LOGGED_OUT_EXIT_STATUS)


def load_credential(user: str, credentials_path: str) -> Credential:
    credentials = CREDENTIALS_SCHEMA.loadf(credentials_path)
    credential = credentials.get(user)
    if credential is None:
        raise Exception(f"Unknown credential user profile {user}")
    return credential


def main(tibia_pid,
         credentials_user,
         credentials_path,
         only_check=False,
         login=False,
         max_wait_minutes=120):
    """Main entry point of the program."""
    tibia_wid = get_tibia_wid(tibia_pid)
    if only_check:
        handle_check(tibia_wid)
    if login:
        if credentials_path is None:
            raise Exception(("A path to a credentials json file is required.\n"
                             "See example: example.credentials.json"))
        if credentials_user is None:
            raise Exception("We require a user profile to login.")

        credential = load_credential(credentials_user, credentials_path)
        handle_login(tibia_wid, credential, max_wait_minutes)


if __name__ == '__main__':
    args = parser.parse_args()
    DEBUG_LEVEL = args.debug_level
    try:
        main(args.pid, args.credentials_user, args.credentials_path,
             args.check_if_ingame, args.login, args.max_wait_minutes)
    except SystemExit as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(FAILURE_EXIT_STATUS)
