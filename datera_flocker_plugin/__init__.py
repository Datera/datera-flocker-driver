# Copyright 2016 Datera Corporation
# See LICENSE file for details.

from flocker.node import BackendDescription, DeployerType
from datera_flocker_plugin.datera_blockdevice import datera_from_configuration


def api_factory(cluster_id, **kwargs):
    return datera_from_configuration(cluster_id=cluster_id,
                                     user=kwargs[u'user'],
                                     password=kwargs[u'password'],
                                     mgmt_addr=kwargs['mgmt_addr'])


FLOCKER_BACKEND = BackendDescription(
    name=u"datera_flocker_plugin",
    needs_reactor=False, needs_cluster_id=True,
    api_factory=api_factory, deployer_type=DeployerType.block)
