#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import netifaces


def _get_interface_mac_broadcast(addrs):
    mac, broadcast = None, None
    if netifaces.AF_LINK in addrs:
        for addr in addrs[netifaces.AF_LINK]:
            mac = addr['addr']
    if netifaces.AF_INET in addrs:
        for addr in addrs[netifaces.AF_INET]:
            broadcast = addr['broadcast']
    return mac, broadcast


def get_udp_mac_address():
    interface, mac, broadcast_address = None, None, None
    for candidate in netifaces.interfaces():
        if candidate.startswith('lo'):
            continue
        mac, broadcast_address = _get_interface_mac_broadcast(netifaces.ifaddresses(candidate))
        if mac is not None and broadcast_address is not None:
            interface = candidate
            break

    if interface is not None:
        return interface, mac, broadcast_address
    else:
        return None, None, None


def get_udp_mac_address_by_interface(interface):
    if interface not in netifaces.interfaces():
        return None, None, None
    else:
        mac, broadcast_address = _get_interface_mac_broadcast(netifaces.ifaddresses(interface))
        return interface, mac, broadcast_address
