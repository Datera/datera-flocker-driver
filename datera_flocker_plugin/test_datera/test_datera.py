# Copyright 2015 Datera Corporation
# See LICENSE file for details.

"""
Functional tests for
``flocker.node.agents.blockdevice.DateraBlockDeviceAPI``
"""

import os
import socket
from uuid import uuid4
from twisted.trial.unittest import SynchronousTestCase, SkipTest
import functools
from flocker.node.agents.test.test_blockdevice import (
        make_iblockdeviceapi_tests
)
from testtools_datera import (
    cleanup_for_test
)


DATERA_ALLOCATION_UNIT = int(1024 * 1024 * 1024)


def daterablockdeviceapi_for_test(test_case):
    """
    Create a ``DateraBlockDeviceAPI`` instance for use in tests.
    :returns: A ``DateraBlockDeviceAPI`` instance
    """
    user_id = os.getuid()
    if user_id != 0:
        raise SkipTest(
            "``DateraBlockDeviceAPI`` queries for iSCSI initiator name \
                           which is owned by root, "
            "Required UID: 0, Found UID: {!r}".format(user_id)
        )
    dfs = cleanup_for_test(test_case)
    return dfs


class DateraBlockDeviceAPIInterfaceTests(
    make_iblockdeviceapi_tests(
        blockdevice_api_factory=functools.partial(
                 daterablockdeviceapi_for_test),
        minimum_allocatable_size=DATERA_ALLOCATION_UNIT,
        device_allocation_unit=DATERA_ALLOCATION_UNIT,
        unknown_blockdevice_id_factory=lambda test: u"vol-00000000"
    )
):

    """
      Interface adherence Tests for ``DateraBlockDeviceAPI``
    """
