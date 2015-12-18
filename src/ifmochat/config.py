#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import logging


def parse_debug_level(s):
    return {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARN,
        'error': logging.ERROR,
    }[s.lower()]


def create_default():
    return {
        "client": {
            "name": None,
            "ui": "console",  # can be: console/console/console/console

            "interface": None,  # if None - interface will be auto-chosen
            "broadcasting_port": 23912,
            "tcp_port": 8239,
        },

        "logging": {
            "filename": None,  # if None - stderr used
            "level": "info",  # can be debug/info/warn/error
            "format": "%(relativeCreated)d [%(threadName)s]\t%(name)s [%(levelname)s]:\t %(message)s",
        }
    }
