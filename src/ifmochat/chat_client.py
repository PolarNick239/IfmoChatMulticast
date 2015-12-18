#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import logging
import asyncio
import functools
import concurrent
import concurrent.futures
from collections import namedtuple

from ifmochat.utils import support
from ifmochat.common import messages
from ifmochat.common.messenger import Messenger, ProtocolMode

logger = logging.getLogger(__name__)


UserInfo = namedtuple('UserInfo', ['name', 'host', 'port'])


class ChatClient:

    def __init__(self, name, port, broadcast_address, broadcast_port, io_executor: support.AsyncExecutor,
                 heartbeat_period=1.0, heartbeat_loss_limit=5):
        self._name = name
        self._port = port

        self._messenger = Messenger(io_executor,
                                    port, ProtocolMode.READ_WRITE,
                                    broadcast_address, broadcast_port, ProtocolMode.READ_WRITE)

        self._user_by_id = {}
        self._user_id_by_host_port = {}
        self._next_id = 1

        self._user_heartbeat_timeout_by_id = {}

        self._heartbeat_period = heartbeat_period
        self._heartbeat_loss_limit = heartbeat_loss_limit

        self._daemon = None

        self._on_messages = set()
        self._on_name_changed = set()
        self._on_user_added = set()
        self._on_user_deleted = set()

    def _get_next_user_id(self):
        cur_id = self._next_id
        self._next_id += 1
        return cur_id

    def _add_user(self, user: UserInfo):
        host_port = (user.host, user.port)
        assert host_port not in self._user_id_by_host_port

        user_id = self._get_next_user_id()
        self._user_by_id[user_id] = user
        self._user_id_by_host_port[host_port] = user_id
        logger.info("User added   user_id={}: {}!".format(user_id, user))

        for handler in self._on_user_added:
            handler(user_id, user)
        return user_id

    def _get_user_id(self, user: UserInfo):
        host_port = (user.host, user.port)
        try:
            user_id = self._user_id_by_host_port[host_port]
            return user_id
        except:
            user_id = self._add_user(user)
            return user_id

    def _delete_user(self, user_id):
        user = self._user_by_id[user_id]
        host_port = (user.host, user.port)

        del self._user_id_by_host_port[host_port]
        del self._user_heartbeat_timeout_by_id[user_id]
        del self._user_by_id[user_id]
        logger.info("User deleted user_id={}: {}!".format(user_id, user))

        for handler in self._on_user_deleted:
            handler(user_id, user)

    def _restart_user_heartbeat_timeout(self, user_id):
        if user_id in self._user_heartbeat_timeout_by_id:
            self._user_heartbeat_timeout_by_id[user_id].cancel()

        self._user_heartbeat_timeout_by_id[user_id] = support.wrap_exc(asyncio.ensure_future(
                support.delayed_coro(
                        self._heartbeat_period * self._heartbeat_loss_limit,
                        functools.partial(self._delete_user, user_id))), logger)

    def _update_author(self, host, message):
        user = UserInfo(message.name, host, message.port)
        user_id = self._get_user_id(user)

        self._restart_user_heartbeat_timeout(user_id)
        old_user = self._user_by_id[user_id]
        if old_user.name != user.name:
            logger.info('User with user_id={} changed name from "{}" to "{}"!'.format(user_id, old_user.name, user.name))
            self._user_by_id[user_id] = user
            for handler in self._on_name_changed:
                handler(user_id, user, old_user.name)

        return user_id, user

    def _handle_message(self, host, message):
        user_id, user = self._update_author(host, message)

        if isinstance(message, messages.TextMessage):
            logger.info('New message from user_id={} {}: "{}"'.format(user_id, user, message.text))
            for handler in self._on_messages:
                handler(user_id, user, message)

    def start(self):
        assert self._daemon is None
        self._messenger.start()
        self._daemon = support.wrap_exc(asyncio.ensure_future(self._run()), logger)

    def stop(self):
        if self._daemon is not None:
            self._daemon.cancel()
            self._daemon = None
        self._messenger.stop()

    @asyncio.coroutine
    def _run(self):
        while True:
            reading = asyncio.ensure_future(self._messenger.take_message())
            heart_beat_timeout = asyncio.ensure_future(asyncio.sleep(self._heartbeat_period))

            with support.auto_cancellation([reading, heart_beat_timeout]):
                done, pending = yield from asyncio.wait([reading, heart_beat_timeout],
                                                        return_when=concurrent.futures.FIRST_COMPLETED)

            if heart_beat_timeout in done:
                logger.debug('Sending heartbeat!')
                yield from self._messenger.send_broadcast(messages.HeartbeatMessage(self._name, self._port))

            if reading in done:
                host_port, message = yield from reading
                logger.info("Message from {}: {}".format(host_port, message))
                self._handle_message(host_port[0], message)

    def get_users(self):
        return self._user_by_id

    def set_name(self, name):
        self._name = name

    @asyncio.coroutine
    def send_message(self, user_id, text):
        user = self._user_by_id[user_id]
        message = messages.TextMessage(self._name, self._port, text)
        host, port = user.host, user.port
        yield from self._messenger.send_message(host, port, message)

    def add_message_handler(self, handler):
        self._on_messages.add(handler)

    def add_name_changed_handler(self, handler):
        self._on_name_changed.add(handler)

    def add_user_added_handler(self, handler):
        self._on_user_added.add(handler)

    def add_user_deleted_handler(self, handler):
        self._on_user_deleted.add(handler)
