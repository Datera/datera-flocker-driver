# Copyright 2016 Datera Corporation
# See LICENSE file for details..

import os
import time
import re
import socket
import platform

from flocker.node.agents.blockdevice import (
    AlreadyAttachedVolume,
    UnknownVolume, UnattachedVolume,
    BlockDeviceVolume,
    IBlockDeviceAPI
)
from eliot import Message, Logger
from twisted.python.filepath import FilePath
from zope.interface import implementer
from subprocess import check_output

from dfs_sdk import DateraApi
from dfs_sdk.exceptions import ApiError

ISCSI_LOGIN_TIME_DELAY = 7
DATERA_ALLOCATION_UNIT = (1024 * 1024 * 1024)
DATERA_CLUSTER_ID = "flocker-"
INITIATOR_FILE = "/etc/iscsi/initiatorname.iscsi"
DISK_BY_PATH = "/dev/disk/by-path"
SYS_BLOCK = "/sys/block"

_logger = Logger()


class DateraConfiguration(object):
    """
    Wrapper object for Datera Configuration
    """

    def __init__(self, cluster_id, user, password, mgmt_addr):
        self.cluster_id = cluster_id
        self.user = user
        self.password = password
        self.mgmt_addr = mgmt_addr


class DeviceException(Exception):
    """
    A base class for exceptions raised by  ``IBlockDeviceAPI`` operations.
    Due to backend device configuration

    :param configuration: DateraConfiguration
           The configuration related to backend device.
    """

    def __init__(self, configuration):
        if not isinstance(configuration, DateraConfiguration):
            raise TypeError(
                'Unexpected configuration type. '
                'Expected DateraConfiguration. '
                'Got {!r}.'.format(AttributeError)
            )
        Exception.__init__(self, configuration)


class DeviceExceptionAPIError(Exception):
    """
    Error on API call
    """


def ensure_acl_exists(si, ii):
    """
    Make sure initiator exists in storage_instance acl
    """
    for i in si.acl_policy.list():
        if ii['path'] in i['initiators']:
            return
    try:
        si.acl_policy.initiators.add(ii)
        Message.new(
            Info='Adding initiator to ACL : ',
            storage_inst=si['name'], initiator=ii['path']).write(_logger)
    except ApiError as ex:
        raise DeviceExceptionAPIError


def login_to_target(si):
    # Give new volume a chance to show up
    time.sleep(ISCSI_LOGIN_TIME_DELAY)
    iqn = si['access']['iqn']
    for ip in si['access']['ips']:
        c = "iscsiadm -m node -T {} --portal {} --op=new"
        c += "  >  /dev/null 2>&1"
        cmd = c.format(iqn, ip)
        os.system(cmd)
        c = "iscsiadm -m node -T {} --portal {} -l > /dev/null 2>&1"
        cmd = c.format(iqn, ip)
        os.system(cmd)
        Message.new(
            Info='iSCSI Login to target : ', target=iqn, ip=ip).write(_logger)


def logout_from_target(si):
    iqn = si['access']['iqn']
    Message.new(
        Info='iSCSI Logout from target : ', target=iqn).write(_logger)
    os.system("iscsiadm -m node -T %s -u > /dev/null 2>&1" % iqn)


def get_datera_appinst(api, ai_name):
    return api.app_instances.list(name=ai_name)[0]


def get_datera_storageinst(api, ai_name):
    ai = get_datera_appinst(api, ai_name)
    return ai.storage_instances.list()[0]


# Assume 1:1:1 app_inst:storage_inst:volume
def get_datera_vol(api, ai_name):
    si = get_datera_storageinst(api, ai_name)
    return si.volumes.list()[0]


# Translate IQN to /dev/sdX entry
def iqn_to_sd(iqn):
    for f in os.listdir(DISK_BY_PATH):
        if iqn in f:
            return os.path.basename(
                os.readlink(DISK_BY_PATH + "/" + f))


# Translate /dev/sdX entry to /dev/dm-X entry
def sd_to_dm(sd):
    for f in os.listdir(SYS_BLOCK):
        t = "{}/{}/slaves/{}".format(SYS_BLOCK, f, sd)
        if os.path.islink(t):
            return f


# Translate /dev/dm-X entry to /dev/mapper/mpathXX
def dm_to_mapper(dm):
    fname = "{}/{}/dm/name".format(SYS_BLOCK, dm)
    with open(fname, 'r') as f:
        mapper = f.read().strip()
    f.closed
    return mapper


@implementer(IBlockDeviceAPI)
class DateraBlockDeviceAPI(object):
    """
    A simulated ``IBlockDeviceAPI`` which manages volumes (devices) with Datera
    """

    VERSION = '1.0'
    driver_name = 'Datera Systems'

    def __init__(self, config, cluster_id,
                 compute_instance_id, allocation_unit):
        """
        :param configuration:
        """
        self._cluster_id = cluster_id
        self._compute_instance_id = unicode(
            check_output(
                ["sed", "-e", "/^#/d", "-e", "s/^.*=//",
                 INITIATOR_FILE]).split()[0])
        self._vols = {}
        self._allocation_unit = int(DATERA_ALLOCATION_UNIT)
        self._config = config
        self._api = DateraApi(username=config.user,
                              password=config.password,
                              hostname=config.mgmt_addr)
        if self._api:
            Message.new(
                Info='Connected to Datera at ' +
                config.mgmt_addr).write(_logger)
            try:
                system = self._api.system.list()[0]
                Message.new(
                    Info='Datera System : ',
                    build_version=system['build_version']).write(_logger)
                Message.new(
                    Info='Datera System : ',
                    cluster_id=str(cluster_id)).write(_logger)
                Message.new(
                    Info='Datera System : ',
                    allocation_unit=self._allocation_unit).write(_logger)
            except ApiError as ex:
                raise DeviceExceptionAPIError
        else:
            Message.new(
                Info='Cannot connect to Datera ',
                ip=config.mgmt_addr,
                username=config.user,
                password=config.password).write(_logger)
            raise DeviceExceptionAPIError

    def _get_vol(self, ai_name):
        """
        Return volume from ai_name
        """
        for i in self._vols:
            if self._vols[i]['ai_name'] == ai_name:
                return self._vols[i]['volume']
        return None

    def _get_vol_details(self, blockdevice_id):
        """
        :param blockdevice_id - volume id
        :return:volume details
        :exception: Unknown volume
        """
        # Need to query storage_instance to find attached initiators

        if not self._known(blockdevice_id):
            raise UnknownVolume(blockdevice_id)

        try:
            ai_name = self._vols[blockdevice_id]['ai_name']
            si = get_datera_storageinst(self._api, ai_name)
            if len(si['active_initiators']) == 0:
                self._vols[blockdevice_id]['attached_to'] = None
            elif len(si['active_initiators']) == 1:
                self._vols[blockdevice_id]['attached_to'] = \
                    si['active_initiators']
            else:
                raise DeviceExceptionAPIError(blockdevice_id)
            volume = self._vols[blockdevice_id]['volume']
            return volume
        except DeviceExceptionObjNotFound as exc:
            raise UnknownVolume(blockdevice_id)

    def _known(self, blockdevice_id):
        return blockdevice_id in self._vols

    def _is_attached(self, blockdevice_id):
        if not self._known(blockdevice_id):
            raise UnknownVolume(blockdevice_id)
        return self._vols[blockdevice_id]['attached_to']

    def _initiator_exists(self, initiator):
        """
        See if initiator exists (or needs to be created)
        """
        for i in self._api.initiators.list():
            if initiator == i['id']:
                return i
        return False

    def _initiator_create(self, initiator):
        """
        Create an initiator
        """
        Message.new(Info=" Creating initiator : ",
                    initiator=initiator).write(_logger)
        return self._api.initiators.create(name=socket.gethostname(),
                                           id=initiator)

    def compute_instance_id(self):
        """
        :return: Compute instance id
        """
        return self._compute_instance_id

    def allocation_unit(self):
        """
        Return allocation unit
        """
        return self._allocation_unit

    def create_volume(self, dataset_id, size):
        try:
            Message.new(
                Info='Creating Volume: ' + str(dataset_id), size=size,
                user=self._config.user, passwd=self._config.password,
                mgmt_addr=self._config.mgmt_addr).write(_logger)
            fname = str(self._cluster_id) + str(dataset_id)
            ai = self._api.app_instances.create(name=fname)
            si = ai.storage_instances.create(name=fname)
            volsize = size / self._allocation_unit
            vol = si.volumes.create(name=fname, size=volsize)
            Message.new(
                Info='Datera API Volume Created: ',
                fname=fname, dataset=str(dataset_id),
                volsize=volsize, size=size).write(_logger)
            blkdev_id = unicode(str(self._cluster_id + vol['uuid']))
            volume = BlockDeviceVolume(
                size=size, attached_to=None,
                dataset_id=dataset_id,
                blockdevice_id=blkdev_id)
            self._vols[blkdev_id] = {'dataset_id': dataset_id,
                                     'size': size,
                                     'attached_to': None,
                                     'ai_name': ai['name'],
                                     'volume': volume}
            Message.new(
                Info='Created volume for ' + str(dataset_id)).write(_logger)
        except ApiError as ex:
            Message.new(
                Info='ERROR creating volume for ' + str(dataset_id),
                resp=ex.message).write(_logger)
            volume = None
            raise DeviceExceptionAPIError

        return volume

    def destroy_volume(self, blockdevice_id):
        """
        Destroy the storage for the given unattached volume.
        :param: blockdevice_id - the volume id
        :raise: UnknownVolume is not found
        """
        if not self._known(blockdevice_id):
            raise UnknownVolume(blockdevice_id)

        ai_name = self._vols[blockdevice_id]['ai_name']
        ai = get_datera_appinst(self._api, ai_name)
        if ai:
            ai.set(admin_state="offline", force=True)
            ai.delete()
            del self._vols[blockdevice_id]
            Message.new(
                Info='Deleted volume ' + blockdevice_id).write(_logger)
        else:
            Message.new(
                Info='ERROR deleting volume ' + blockdevice_id).write(_logger)
            raise UnknownVolume(blockdevice_id)

    def destroy_volume_folder(self):
        """
        Destroy the volume folder
        :param: none
        """
        return

    def attach_volume(self, blockdevice_id, attach_to):
        """
        1)  Add initiator to storage instance
        2)  Login
        """

        if self._is_attached(blockdevice_id):
            raise AlreadyAttachedVolume(blockdevice_id)

        if not self._known(blockdevice_id):
            raise UnknownVolume(blockdevice_id)

        ai_name = self._vols[blockdevice_id]['ai_name']
        si = get_datera_storageinst(self._api, ai_name)

        ii = self._initiator_exists(attach_to)
        if not ii:
            ii = self._initiator_create(attach_to)
            if not ii:
                raise DeviceExceptionAPIError(attach_to)
        Message.new(
            Info=' adding initiator : ',
            attached_to=attach_to).write(_logger)
        ensure_acl_exists(si, ii)
        login_to_target(si)
        self._vols[blockdevice_id]['attached_to'] = attach_to
        volume = BlockDeviceVolume(
            size=self._vols[blockdevice_id]['size'],
            attached_to=attach_to,
            dataset_id=self._vols[blockdevice_id]['dataset_id'],
            blockdevice_id=blockdevice_id)
        self._vols[blockdevice_id]['volume'] = volume
        Message.new(
            Info=' attach_volume', vol=blockdevice_id,
            attached_to=attach_to).write(_logger)
        return volume

    def resize_volume(self, blockdevice_id, size):
        return

    def detach_volume(self, blockdevice_id):
        """
        :param: volume id = blockdevice_id
        :raises: unknownvolume exception if not found

        """

        if not self._is_attached(blockdevice_id):
            Message.new(
                Info="Volume" + blockdevice_id + "not attached").write(_logger)
            raise UnattachedVolume(blockdevice_id)

        ai_name = self._vols[blockdevice_id]['ai_name']
        si = get_datera_storageinst(self._api, ai_name)
        logout_from_target(si)
        volume = BlockDeviceVolume(
            size=self._vols[blockdevice_id]['size'],
            attached_to=None,
            dataset_id=self._vols[blockdevice_id]['dataset_id'],
            blockdevice_id=blockdevice_id)
        self._vols[blockdevice_id]['volume'] = volume
        self._vols[blockdevice_id]['attached_to'] = None
        Message.new(
            Info=' detach_volume', vol=blockdevice_id).write(_logger)

    def list_volumes(self):
        """
        Return ``BlockDeviceVolume`` instances for all the files in the
        ``unattached`` directory and all per-host directories.

        See ``IBlockDeviceAPI.list_volumes`` for parameter and return type
        documentation.
        """
        volumes = []
        try:
            for ai in self._api.app_instances.list():
                if self._cluster_id in ai['name']:
                    volume = self._get_vol(ai['name'])
                    if volume:
                        volumes.append(volume)
        except Exception as exe:
            pass
        return volumes

    def get_device_path(self, blockdevice_id):
        """
        :param blockdevice_id:
        :return:the device path
        """
        if not self._known(blockdevice_id):
            raise UnknownVolume(blockdevice_id)

        # Datera mulitpath resolution
        # Get the IQN
        # Translate to host sdXX
        # Translate to dm-X
        # Translate to mpathXX
        ai_name = self._vols[blockdevice_id]['ai_name']
        try:
            si = get_datera_storageinst(self._api, ai_name)
            iqn = si['access']['iqn']
        except ApiError as ex:
            raise DeviceExceptionAPIError
        sd = iqn_to_sd(iqn)
        if not sd:
            raise UnattachedVolume(blockdevice_id)
        dm = sd_to_dm(sd)
        if not dm:
            raise UnattachedVolume(blockdevice_id)
        mpath = dm_to_mapper(dm)
        if mpath:
            return FilePath("/dev/mapper/" + mpath)
        raise UnattachedVolume(blockdevice_id)


def datera_from_configuration(cluster_id, user, password, mgmt_addr):
    """
    :param cluster_id:
    :param user:
    :param password:
    :param mgmt_addr:
    :return:DateraBlockDeviceAPI object
    """
    return DateraBlockDeviceAPI(
        config=DateraConfiguration(cluster_id, user, password, mgmt_addr),
        cluster_id=str(DATERA_CLUSTER_ID),
        compute_instance_id=unicode(socket.gethostname()),
        allocation_unit=DATERA_ALLOCATION_UNIT
    )
