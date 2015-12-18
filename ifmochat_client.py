#
# Copyright (c) 2015, Nikolay Polyarnyi
# All rights reserved.
#

import sys
import yaml
import asyncio
import logging

from ifmochat import config
from ifmochat import chat_client
from ifmochat.gui.console import ConsoleUI
from ifmochat.utils import support, udp_interface


logger = logging.getLogger(__name__)


def main(cfg):
    client_config = cfg['client']

    interface = client_config['interface']
    if interface is not None:
        interface, _, udp_address = udp_interface.get_udp_mac_address_by_interface(interface)
    else:
        interface, _, udp_address = udp_interface.get_udp_mac_address()

    if interface is None:
        logger.error("No broadcast interface found!")
        return
    else:
        logger.info("Used interface={} address={}".format(interface, udp_address))

    name = client_config['name']
    tcp_port = client_config['tcp_port']
    broadcasting_port = client_config['broadcasting_port']

    if name is None:
        logger.error("Name is None! Configure your name in config!")
        return

    io_executor = support.AsyncExecutor(8)
    client = chat_client.ChatClient(name, tcp_port, udp_address, broadcasting_port,
                                    io_executor)

    if client_config['ui'] == 'console':
        ui = ConsoleUI(client, io_executor)
    else:
        logger.error("Incorrect client/ui='{}' value in config!".format(client_config['ui']))
        return

    client.start()
    asyncio.get_event_loop().run_until_complete(ui.run())

    io_executor.shutdown(wait=False)
    client.stop()
    asyncio.get_event_loop().stop()


if __name__ == '__main__':
    args = sys.argv
    if len(args) != 2:
        print('Usage: [config]\n')
    else:
        config_path = sys.argv[1]
        with open(config_path) as f:
            cfg = yaml.load(f)
        cfg = support.deep_merge(config.create_default(), cfg)

        params = {'level': config.parse_debug_level(cfg['logging']['level']),
                  'format': cfg['logging']['format']}
        if cfg['logging']['filename'] is not None:
            params['filename'] = cfg['logging']['filename']
        logging.basicConfig(**params)

        main(cfg)
