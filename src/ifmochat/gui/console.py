#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import asyncio
import functools
import logging

from ifmochat.chat_client import ChatClient
from ifmochat.common import messages
from ifmochat.utils import support
from ifmochat.utils.support import AsyncExecutor


logger = logging.getLogger(__name__)


class ConsoleUI:

    def __init__(self, client: ChatClient, io_executor: AsyncExecutor):
        self._client = client
        self._io_executor = io_executor

        self._next_message_id = 1

    def _get_message_id(self):
        cur_id = self._next_message_id
        self._next_message_id += 1
        return cur_id

    @asyncio.coroutine
    def _read_command(self, prompt=""):
        line = yield from self._io_executor.map(input, prompt)
        return line

    def _print_help(self):
        print("> Commands:\n"
              "    help              - prints this help (shortcut - '?' and 'h')\n"
              "    exit              - exit (shortcut - 'e' and 'q')\n"
              "    users             - prints online users list (shortcut - 'u')\n"
              "    name [new_name]   - change name to new one (shortcut is 'n')\n"
              "    send [user_id]    - then type message followed with enter to send message,\n"
              "                        to see users ids - use 'users'-command (shortcut is 's' or simply print <user_id>),\n"
              "                        to cancel sending a message - press enter with empty message\n")

    def _print_users(self):
        users = self._client.get_users()
        print("> Users:")
        print("id\tname\tport\thost")
        for user_id, user in users.items():
            print("{}:\t{}\t{}\t{}".format(user_id, user.name, user.port, user.host))

    def _change_name(self, name):
        self._client.set_name(name)

    def _get_user_name(self, user_id):
        user = self._client.get_users()[user_id]
        return user.name

    def _send_message(self, user_id, message_text):
        message_id = self._get_message_id()
        send_task = support.wrap_exc(asyncio.ensure_future(
                self._client.send_message(user_id, message_text)), logger)
        send_task.add_done_callback(functools.partial(
                self._on_message_sended, user_id, message_id))

    def _on_message_sended(self, user_id, message_id, f: asyncio.Future):
        if f.exception() is not None:
            print("> Failure with message {} to user_id={}!"
                  .format(self._next_message_id - message_id, user_id))

    def _print_message(self, user_id, user, message):
        assert isinstance(message, messages.TextMessage)
        text = message.text
        print("> {} {}: {}".format(user_id, user.name, text))

    def _print_name_changed(self, user_id, user, old_name):
        print("> {} {}: changed name to '{}'".format(user_id, old_name, user.name))

    def _print_user_online(self, user_id, user):
        print("> {} {}: online!".format(user_id, user.name))

    def _print_user_offline(self, user_id, user):
        print("> {} {}: offline!".format(user_id, user.name))


    @asyncio.coroutine
    def run(self):
        self._print_help()
        self._client.add_message_handler(self._print_message)
        self._client.add_name_changed_handler(self._print_name_changed)
        self._client.add_user_added_handler(self._print_user_online)
        self._client.add_user_deleted_handler(self._print_user_offline)
        while True:
            line = yield from self._read_command()
            if line.startswith("h") or line.startswith("?"):
                self._print_help()
            elif line.startswith("e") or line.startswith("q"):
                return
            elif line.startswith("u"):
                self._print_users()
            elif line.startswith("n"):
                name = line.split(" ", 1)[1]
                self._change_name(name)
            elif len(line) > 0:
                if line.startswith("s"):
                    user_id = line.split(" ")[1]
                else:
                    user_id = line
                try:
                    user_id = int(user_id)
                except ValueError:
                    print("> User id should be integer, but found '{}'!".format(user_id))
                    continue

                try:
                    print("> Message to {}:".format(self._get_user_name(user_id)))
                    message = yield from self._read_command()
                    if len(message) == 0:
                        print("> Canceled!")
                        continue
                    self._send_message(user_id, message)
                except KeyError:
                    print("> User not found!")
                    self._print_users()
