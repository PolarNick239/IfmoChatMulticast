#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#


import json
from collections import namedtuple


_messages_serial_code = 157342

Message = namedtuple('Message', ('name', 'port'))

HeartbeatMessage = namedtuple('HeartbeatMessage', Message._fields + ())

TextMessage = namedtuple('TextMessage', Message._fields + ('text',))


_MESSAGES_CLASSES = [HeartbeatMessage,
                     TextMessage,
                     ]

_NAME_TO_CLASS = {
    clazz.__name__: clazz
    for clazz in _MESSAGES_CLASSES
}


def serialize_message(message, encoding='utf-8'):
    return json.dumps({'clazz': message.__class__.__name__,
                       'message': message,
                       'serial_code': _messages_serial_code,
                       }).encode(encoding)


def deserialize_message(data_bytes, encoding='utf-8'):
    state = json.loads(data_bytes.decode(encoding=encoding))
    assert state['serial_code'] == _messages_serial_code
    clazz = _NAME_TO_CLASS[state['clazz']]
    return clazz(*state['message'])
