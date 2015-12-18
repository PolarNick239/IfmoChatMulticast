#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#


def _check_serial_code(self, state):
    clazz = self.__class__
    serial_code = clazz.serial_code
    assert serial_code == state['serial_code']


def create_object(clazz, state):
    obj = clazz.__new__(clazz)
    _check_serial_code(obj, state)
    obj.__setstate__(state)
    return obj
