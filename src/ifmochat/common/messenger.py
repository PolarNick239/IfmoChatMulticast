#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import json
import socket
import asyncio
import logging
import concurrent
from enum import Enum
import concurrent.futures
from abc import abstractmethod

from ifmochat.utils import support
from ifmochat.common import messages

_BROADCAST_MESSAGE_SIZE_LIMIT = 4 * 1024


class ProtocolMode(Enum):
    READ_ONLY = "r"
    WRITE_ONLY = 'w'
    READ_WRITE = 'rw'
    DISABLED = 'off'


class ProtocolListener:

    def __init__(self, mode: ProtocolMode):
        self._daemon = None
        self._address_message_queue = asyncio.Queue()
        self._mode = mode

    def start(self):
        if self._mode in [ProtocolMode.READ_ONLY, ProtocolMode.READ_WRITE]:
            self._daemon = support.wrap_exc(asyncio.ensure_future(self._listen_messages()), self._get_logger())

    @abstractmethod
    def _listen_message(self):
        pass

    @asyncio.coroutine
    def _listen_messages(self):
        while True:
            address, data_bytes = yield from self._listen_message()
            message = self._deserialize(data_bytes)
            self._address_message_queue.put_nowait((address, message))

    @asyncio.coroutine
    def take_message(self):
        assert self._mode in [ProtocolMode.READ_ONLY, ProtocolMode.READ_WRITE]
        address, message = yield from self._address_message_queue.get()
        self._get_logger().debug('Taking  message: {}...'.format(message))
        return address, message

    def _deserialize(self, data_bytes):
        self._get_logger().debug('Parsing message: {}...'.format(json.loads(data_bytes.decode())))
        message = messages.deserialize_message(data_bytes)
        self._get_logger().debug('Parsed  message: {}!'.format(message))
        return message

    def stop(self):
        if self._daemon is not None:
            self._daemon.cancel()
            self._daemon = None

    @abstractmethod
    def _get_logger(self):
        pass


class TCPMessenger(ProtocolListener):

    def __init__(self, port, mode: ProtocolMode, io_executor: support.AsyncExecutor, connection_timeout=2.0):
        super().__init__(mode)
        self._port = port
        self._io_executor = io_executor
        self._connection_timeout = connection_timeout

        self._loop = asyncio.get_event_loop()

        self._server_socket = None

        self._logger = logging.getLogger('TCPMessenger{}'.format(self._port))

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.bind(('', self._port))  # TODO: '' should be replaced with self._inet_address
        self._server_socket.setblocking(1)

        self._server_socket.listen(1)
        self._logger.debug('Listening...')
        super(TCPMessenger, self).start()

    @asyncio.coroutine
    def _listen_message(self):
        conn, address = yield from self._io_executor.map(self._server_socket.accept)
        conn.setblocking(1)
        self._logger.debug('Accepted connection from {}!'.format(address))
        data_bytes = b''
        with conn:
            while True:
                part = yield from self._io_executor.map(conn.recv, 1024)
                if not part:
                    break
                else:
                    data_bytes += part
        self._logger.debug('Received {} bytes from {}!'.format(len(data_bytes), address))
        return address, data_bytes

    @asyncio.coroutine
    def send_message(self, host, port, message):
        assert self._mode in [ProtocolMode.WRITE_ONLY, ProtocolMode.READ_WRITE]

        data_bytes = messages.serialize_message(message)
        self._logger.debug('Connecting to {}:{} (to send {} bytes)...'.format(host, port, len(data_bytes)))
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setblocking(1)
        with client_socket:
            address = yield from self._loop.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
            self._logger.debug('Connecting... {}'.format(address))

            assert len(address) == 1
            address = address[0]

            client_socket.settimeout(self._connection_timeout)
            try:
                yield from self._io_executor.map(client_socket.connect, address[4])

                self._logger.debug('Sending data... ({} bytes)'.format(len(data_bytes)))
                yield from self._io_executor.map(client_socket.sendall, data_bytes)
                self._logger.debug('Data sent!')
            except Exception as e:
                self._logger.warn('Exception occurred while sending data to {}!'.format(host),
                                  exc_info=support.exc_info(e))
                return False
        self._logger.debug('Sent {} bytes to {}!'.format(len(data_bytes), address[4]))
        return True

    def _get_logger(self):
        return self._logger

    def stop(self):
        super(TCPMessenger, self).stop()
        self._server_socket.close()


class UDPMessenger(ProtocolListener):

    def __init__(self, broadcast_address, port, mode: ProtocolMode, io_executor: support.AsyncExecutor):
        super().__init__(mode)
        self._broadcast_address = broadcast_address
        self._port = port
        self._io_executor = io_executor
        self._loop = asyncio.get_event_loop()

        self._broadcast_socket = None
        self._listening_broadcast_socket = None

        self._logger = logging.getLogger('UDPMessenger{}'.format(self._port))
    
    def start(self):
        if self._mode in [ProtocolMode.WRITE_ONLY, ProtocolMode.READ_WRITE]:
            self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._broadcast_socket.setblocking(1)

        if self._mode in [ProtocolMode.READ_ONLY, ProtocolMode.READ_WRITE]:
            self._listening_broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # TODO: '' should be replaced with self._inet_address:
            self._listening_broadcast_socket.bind(('', self._port))
            self._listening_broadcast_socket.setblocking(1)

        super(UDPMessenger, self).start()

    @asyncio.coroutine
    def _listen_message(self):
        data_bytes, address = yield from self._io_executor.map(
            self._listening_broadcast_socket.recvfrom, _BROADCAST_MESSAGE_SIZE_LIMIT)
        self._logger.debug('Received {} bytes from {}!'.format(len(data_bytes), address))
        return address, data_bytes

    @asyncio.coroutine
    def send_message(self, message):
        assert self._mode is not ProtocolMode.READ_ONLY

        data_bytes = messages.serialize_message(message)
        assert len(data_bytes) <= _BROADCAST_MESSAGE_SIZE_LIMIT
        broadcast_address = (self._broadcast_address, self._port)

        self._logger.debug('Sending {} bytes to broadcast...'.format(len(data_bytes)))
        yield from self._io_executor.map(
            self._broadcast_socket.sendto, data_bytes, broadcast_address)
        self._logger.debug('{} bytes message broadcast!'.format(len(data_bytes)))

    def _get_logger(self):
        return self._logger

    def stop(self):
        super(UDPMessenger, self).stop()
        if self._broadcast_socket is not None:
            self._broadcast_socket.close()
        if self._listening_broadcast_socket is not None:
            self._listening_broadcast_socket.close()


class Messenger:

    def __init__(self, io_executor: support.AsyncExecutor,
                 tcp_port, tcp_mode: ProtocolMode,
                 udp_address, udp_port, udp_mode: ProtocolMode):
        self._tcp_mode = tcp_mode
        self._tcp_messenger = TCPMessenger(tcp_port, tcp_mode, io_executor)
        self._udp_mode = udp_mode
        self._udp_messenger = UDPMessenger(udp_address, udp_port, udp_mode, io_executor)
        self._logger = logging.getLogger('Messenger')

        self._logger.info('Creating messengers...')

        self._daemon = None
        self._address_message_queue = asyncio.Queue()

    def start(self):
        self._logger.info('Starting messengers...')
        self._tcp_messenger.start()
        self._udp_messenger.start()
        self._logger.info('Messengers started!')
        self._daemon = support.wrap_exc(asyncio.ensure_future(self._taking_messages_loop()), self._logger)

    def stop(self):
        if self._daemon is not None:
            self._daemon.cancel()
            self._daemon = None
        self._tcp_messenger.stop()
        self._udp_messenger.stop()

    @asyncio.coroutine
    def _taking_messages_loop(self):
        while True:
            takings = []
            for mode, listener in [(self._tcp_mode, self._tcp_messenger), (self._udp_mode, self._udp_messenger)]:
                if mode in [ProtocolMode.READ_ONLY, ProtocolMode.READ_WRITE]:
                    takings.append(support.wrap_exc(asyncio.ensure_future(
                            listener.take_message()), self._logger))

            with support.auto_cancellation(takings):
                done, pending = yield from asyncio.wait(takings, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                address, message = yield from f
                self._address_message_queue.put_nowait((address, message))
                self._logger.debug(
                    'Message {} putted. Queue size: {}.'.format(message, self._address_message_queue.qsize()))

    @asyncio.coroutine
    def take_message(self):
        address, message = yield from self._address_message_queue.get()
        self._logger.debug('Taking message from {}: {}...'.format(address, message))
        return address, message

    @asyncio.coroutine
    def send_broadcast(self, message):
        yield from self._udp_messenger.send_message(message)

    @asyncio.coroutine
    def send_message(self, host, port, message):
        self._logger.debug('Sending message to {}:{} message={}...'.format(host, port, message))
        success = yield from self._tcp_messenger.send_message(host, port, message)
        if not success:
            self._logger.debug('Sending message to {}:{} failed!'.format(host, port))
        return success
