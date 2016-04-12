# Copyright 2016 Datera Corporation
# See LICENSE file for details.

"""
Datera Test helpers for ``flocker.node.agents``.
"""

import os
import yaml
import socket

from twisted.trial.unittest import SkipTest

from datera_flocker_plugin.datera_blockdevice import (
    DateraBlockDeviceAPI,
    DateraConfiguration
)


def datera_config_from_environment():
    """
    Connect to Datera through Python SDK.
    Config file comes from environment

    :returns:DateraConfiguration Object
    """
    config_file_path = os.environ.get('DATERA_FLOCKER_CFG')
    if config_file_path is not None:
        config_file = open(config_file_path)
    else:
        raise SkipTest(
            'Supply the path to config file '
            'using the DATERA_FLOCKER_CFG environment variable. '
            'See: '
            'https://docs.clusterhq.com/en/latest/gettinginvolved/acceptance-testing.html '  # noqa
            'for details of the expected format.'
        )
    config = yaml.load(config_file.read())
    datera_config = config['datera']
    datera_username = datera_config['user']
    datera_password = datera_config['password']
    datera_mgmt_addr = datera_config['mgmt_addr']
    datera_cluster_id = datera_config['cluster_id']

    return DateraConfiguration(datera_cluster_id,
                               datera_username,
                               datera_password,
                               datera_mgmt_addr)


def detach_destroy_volumes(api):
    """
    Detach and destroy all volumes known to this API.
    :param : api object
    """
    volumes = api.list_volumes()

    for volume in volumes:
        if volume.attached_to is not None:
            api.detach_volume(volume.blockdevice_id)
        api.destroy_volume(volume.blockdevice_id)


def cleanup_for_test(test_case):
    """
    Return a ``Datera Client`and register a ``test_case``
    cleanup callback to remove any volumes that are created during each test.
    :param test_case object
    """
    config = datera_config_from_environment()
    datera = DateraBlockDeviceAPI(
        cluster_id=config.cluster_id,
        config=config,
        compute_instance_id=unicode(socket.gethostname()),
        allocation_unit=None)
    test_case.addCleanup(detach_destroy_volumes, datera)

    return datera
