Datera Flocker Plugin
======================


## Installation
- Install OpeniSCSI
    * Ubuntu
   ```bash
    sudo apt-get update
    sudo apt-get install -y open-iscsi
    sudo apt-get install -y lsscsi
    sudo apt-get -y install device-mapper-multipath
    ```
    * Centos
    ```bash
    sudo yum check-update
    sudo yum -y install iscsi-initiator-utils
    sudo yum -y install lsscsi
    sudo yum -y install device-mapper-multipath
    ```
- Install ClusterHQ/Flocker
      

             Refer to install notes :
                    https://docs.clusterhq.com/en/latest/docker-integration/install-node.html

- Install Prerequisits tools

    [Some of these steps may have been completed, as per the previous step]

    ```bash
    if selinuxenabled; then setenforce 0; fi
    test -e /etc/selinux/config && \
        sed --in-place='.preflocker' 's/^SELINUX=.*$/SELINUX=disabled/g' /etc/selinux/config
    yum clean all
    yum install -y \
        https://clusterhq-archive.s3.amazonaws.com/centos/clusterhq-release$(rpm -E %dist).noarch.rpm
    yum install -y clusterhq-flocker-node
    systemctl enable docker.service
    systemctl start docker.service
    ```
- Install Datera Plugin

Flocker comes with its own Python context.
Flocker also depends on the ClusterHQ forked repository of 'testtools'
You must install the plugin and Datera Python SDK within the Flocker Python context.
You CANNOT use the default Python command.

```bash
    git clone https://github.com/datera/python-sdk
    cd python-sdk
    sudo /opt/flocker/bin/python2.7 setup.py install
    cd ..
    git clone https://github.com/datera/datera-flocker-driver
    cd datera-flocker-driver
    sudo /opt/flocker/bin/pip install --upgrade --process-dependency-links .[dev] \
           git+https://github.com/ClusterHQ/testtools@clusterhq-fork#egg=testtools-1.8.2chq2
    sudo /opt/flocker/bin/python2.7 setup.py install
```

## Usage Instructions
To start the plugin on a node, a configuration file must exist on the node at /etc/flocker/agent.yml. This should be as follows, replacing __${datera_ip}__,   __${datera_user}__ and   __${datera_password}__ with the ip/hostname, username and password of Datera Mgmt IP port:
```bash
version: 1
control-service:
   hostname: ${FLOCKER_CONTROL_NODE}
dataset:
   backend: datera_flocker_plugin
   mgmt_addr: ${datera_ip}
   user: ${datera_user}
   password: ${datera_password}
   cluster_id: "flocker-"
```

## Running Tests

Setup the config file (edit values for your environment)
```bash
export DATERA_FLOCKER_CFG=/etc/flocker/datera.yml
vi $DATERA_FLOCKER_CFG
datera:
  user: ${Datera_USERNAME}
  password: ${Datera_PASSWORD}
  mgmt_ip: ${Datera_MGMT_IP}
```
Run the tests
```bash
cd datera_flocker_plugin
/opt/flocker/bin/trial datera_flocker_plugin.test_datera
```
You should see below if all was succesfull

PASSED (successes=27)


## Future

## Contribution
Create a fork of the project into your own reposity. Make all your necessary changes and create a pull request with a description on what was added or removed and details explaining the changes in lines of code. If approved, project owners will merge it.

## Licensing
**Datera will not provide legal guidance on which open source license should be used in projects. We do expect that all projects and contributions will have a valid open source license, or align to the appropriate license for the project/contribution**

Copyright [2015] [Datera Corporation]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Support
Please file bugs and issues at the Github issues page. For more general discussions you can contact the Flocker team at <a href="https://groups.google.com/forum/#!forum/flocker-users">Google Groups</a> or tagged with **Datera** on <a href="https://stackoverflow.com">Stackoverflow.com</a>. The code and documentation are released with no warranties or SLAs and are intended to be supported through a community driven process.