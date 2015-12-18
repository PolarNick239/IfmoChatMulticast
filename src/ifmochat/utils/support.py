#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import asyncio
import logging
from itertools import chain

import functools
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def wrap_exc(f: asyncio.Future, logger):
    def check_exception(f: asyncio.Future):
        if not f.cancelled() and f.exception() is not None:
            logger.error('Exception!',
                         exc_info=exc_info(f.exception()))

    f.add_done_callback(check_exception)
    return f


def exc_info(exception):
    if exception is None:
        return None
    assert isinstance(exception, BaseException)
    return type(exception), exception, exception.__traceback__


@contextmanager
def auto_cancellation(fs):
    yield
    for f in fs:
        if f is not None:
            logger.debug("canceled: {}".format(f.cancel()))


@asyncio.coroutine
def delayed_coro(delay_seconds, foo_or_coro):
    yield from asyncio.sleep(delay_seconds)
    if asyncio.iscoroutine(foo_or_coro):
        yield from foo_or_coro
    else:
        foo_or_coro()


class AsyncExecutor:

    def __init__(self, max_workers, loop: asyncio.events.AbstractEventLoop=None):
        self._executor = ThreadPoolExecutor(max_workers)
        self._loop = loop or asyncio.get_event_loop()

    def __del__(self):
        self.shutdown()

    @asyncio.coroutine
    def map(self, fn, *args, **kwargs):
        result = yield from self._loop.run_in_executor(self._executor, functools.partial(fn, *args, **kwargs))
        return result

    def shutdown(self, wait=True):
        if self._executor is None:
            return False
        else:
            self._executor.shutdown(wait=wait)
            self._executor = None
            return True


def str_dict(d: dict):
    """
    >>> str_dict({1: 1, "1": "1"})
    "{'1': '1', 1: 1}"
    >>> str_dict({(2, 3): "1", 1: "2", 2: "3", "a": "4", "b": {"1": 1}})
    "{'a': '4', 'b': {'1': 1}, (2, 3): '1', 1: '2', 2: '3'}"
    """
    def to_str(x):
        if isinstance(x, str):
            return "'" + x + "'"
        else:
            return str(x)

    result = "{"
    for i, key in enumerate(sorted(d.keys(), key=to_str)):
        value = d[key]

        if isinstance(value, dict):
            value = str_dict(value)
        else:
            value = to_str(value)

        if i > 0:
            result += ", "
        result += "{}: {}".format(to_str(key), value)
    return result + "}"


def deep_merge(base_dict: dict, new_dict: dict):
    """
    >>> str_dict(deep_merge({1: "old", 2: "only_old"}, {1: "new", 3: "only_new"}))
    "{1: 'new', 2: 'only_old', 3: 'only_new'}"
    >>> str_dict(deep_merge({"inner": {1: "old", 2: "only_old"}}, {"inner": {1: "new", 3: "only_new"}}))
    "{'inner': {1: 'new', 2: 'only_old', 3: 'only_new'}}"
    >>> result = deep_merge({1: 0, 2: 0, 3: 239, 'd': {"d1": 1, "d2": 2}}, {1: 1, 2: -1, 239: 2012, 'd': {"d1": 3, "d3": 4}})
    >>> str_dict(result)
    "{'d': {'d1': 3, 'd2': 2, 'd3': 4}, 1: 1, 2: -1, 239: 2012, 3: 239}"
    """
    result = {}
    for key in set(chain(base_dict.keys(), new_dict.keys())):
        if key in new_dict:
            value = new_dict[key]
        else:
            value = base_dict[key]
        if isinstance(value, dict) and key in base_dict and key in new_dict:
            value = deep_merge(base_dict[key], new_dict[key])
        result[key] = value
    return result
