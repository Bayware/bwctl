"""
This module implements configuration handling
"""

import getpass
import os
import socket
from functools import reduce
from typing import Any, Dict

import requests
import yaml
from bwctl.utils.common import dump_dict_to_file, log_error, log_info


class Config:
    """Define config object"""

    def __init__(self, version: str, version_family: str):
        """Initialise all attributes"""
        # Initialize versions
        self.version: str = version
        self.version_family: str = version_family

        # File names
        self.dir: str = os.path.expanduser("~/.bwctl/")
        self.file: str = os.path.join(self.dir, 'config')

        # Ensure configuration directory exists
        try:
            os.makedirs(self.dir)
        except FileExistsError:
            # directory already exists
            pass

        # Initialise configuration
        self.config: Dict = {}
        try:
            with open(self.file, 'r') as config_f:
                self.config = yaml.safe_load(config_f)
            config_f.close()
        except FileNotFoundError:
            log_info("No configuration file found, starting clean")
            self.config = {}

    def __repr__(self) -> str:
        """"String reputation of an object"""
        return u"{}".format(self.config)

    def dump(self) -> bool:
        """Dump configuration to a file"""
        return dump_dict_to_file(self.file, self.config)

    def get(self) -> Dict:
        """Get application configuration"""
        return self.config

    def get_attr(self, keys: str) -> Any:
        """Returns configuration dictionary nested values represented as dot separated string, False otherwise"""
        return reduce(
            lambda d, key: d.get(key, False) if isinstance(d, dict) else False,
            keys.split("."),
            self.config
        )

    def get_branch(self) -> str:
        """Get application configuration branch"""
        return self.get_attr('components.branch')

    def get_family(self) -> str:
        """Get application configuration family version"""
        return self.get_attr('components.family')

    def get_current_fabric(self) -> str:
        """Get application configuration current fabric"""
        return self.get_attr('current_fabric')

    def get_debug(self) -> str:
        """Get application configuration debug"""
        return self.get_attr('debug')

    def init(self) -> bool:
        """Init configuration state"""
        if not self.init_attr_fabric_manager():
            return False
        self.init_attr_components()
        self.init_attr_credentials()
        self.init_attr_current_fabric()
        self.init_attr_debug()
        self.init_attr_hosted_zone()
        self.init_attr_marketplace()
        self.init_attr_os_type()
        self.init_attr_production()
        self.init_attr_cloud_storage()
        self.init_attr_ssh_keys()
        self.init_attr_username()
        return True

    def init_attr_fabric_manager(self) -> bool:
        """Init configuration attributes for fabric manager"""
        # Set default value
        fabric_manager: Dict = {}
        if not bool(self.get_attr('fabric_manager')):
            self.set_attr('fabric_manager', fabric_manager, override=False)
        fabric_manager = self.get_attr('fabric_manager')
        if 'id' not in fabric_manager or 'ip' not in fabric_manager:
            hostname: str = socket.gethostname()
            username: str = getpass.getuser()
            try:
                ip: str = requests.get('https://api.ipify.org').text
            except (requests.ConnectionError, requests.ConnectionError, requests.HTTPError, requests.URLRequired,
                    requests.Timeout, requests.TooManyRedirects) as l_err:
                log_error("Unexpected error: Not able to get fabric manager's IP address ({0!s})".format(l_err))
                return False
            fabric_manager['id'] = hostname + '_' + ip + '_' + username
            fabric_manager['ip'] = ip
        if 'company_name' not in fabric_manager:
            fabric_manager['company_name'] = ''
        self.set_attr('fabric_manager', fabric_manager, override=True)
        return True

    def init_attr_components(self) -> bool:
        """Init configuration attribute components"""
        # Set default values
        branch: str = 'master'
        if int(self.version.split('.')[1]) % 2 == 0:
            branch = 'release'
        family: str = self.version_family.split('.')[0] + '.' + self.version_family.split('.')[1]
        # Check branch
        if bool(self.get_attr('components.branch')):
            branch = self.get_attr('components.branch')
        # Check family
        if bool(self.get_attr('components.family')):
            family = self.get_attr('components').get('family')
        self.set_attr('components', {'branch': branch, 'family': family}, override=False)
        return True

    def init_attr_credentials(self) -> bool:
        """Init configuration attribute credentials_file"""
        # Set default value
        if not bool(self.get_attr('credentials_file')):
            self.set_attr('credentials_file', '~/.bwctl/credentials.yml', override=False)
        return True

    def init_attr_current_fabric(self) -> bool:
        """Init configuration attribute current_fabric"""
        # Set default value
        if not bool(self.get_attr('current_fabric')):
            self.set_attr('current_fabric', None, override=False)
        return True

    def init_attr_debug(self) -> bool:
        """Init configuration attribute debug"""
        # Set default value
        if not bool(self.get_attr('debug')):
            self.set_attr('debug', False, override=False)
        return True

    def init_attr_hosted_zone(self) -> bool:
        """Init configuration attribute hosted_zone"""
        # Set default value
        if not bool(self.get_attr('hosted_zone')):
            self.set_attr('hosted_zone', 'poc.bayware.io', override=False)
        return True

    def init_attr_marketplace(self) -> bool:
        """Init configuration attribute marketplace"""
        # Set default value
        if not bool(self.get_attr('marketplace')):
            self.set_attr('marketplace', False, override=False)
        return True

    def init_attr_os_type(self) -> bool:
        """Init configuration attribute os_type"""
        # Set default value
        if not bool(self.get_attr('os_type')):
            self.set_attr('os_type', 'ubuntu', override=False)
        return True

    def init_attr_production(self) -> bool:
        """Init configuration attribute production"""
        # Set default value
        if not bool(self.get_attr('production')):
            self.set_attr('production', True, override=False)
        return True

    def init_attr_cloud_storage(self) -> bool:
        """Init configuration attributes for state cloud storage"""
        # Set default value
        if not bool(self.get_attr('cloud_storage')):
            cloud_storage: Dict = {
                'state': {
                    'enabled': False,
                    'bucket': 'terraform-states-sandboxes',
                    'region': 'us-west-1'
                },
                'terraform': {
                    'enabled': True,
                    'bucket': 'terraform-states-sandboxes',
                    'region': 'us-west-1'
                }
            }
            self.set_attr('cloud_storage', cloud_storage, override=False)
        return True

    def init_attr_ssh_keys(self) -> bool:
        """Init configuration attribute ssh_keys"""
        # Set default value
        if not bool(self.get_attr('ssh_keys')):
            self.set_attr('ssh_keys', {'private_key': ''}, override=False)
        return True

    def init_attr_username(self) -> bool:
        """Init configuration attribute username"""
        # Set default value
        if not bool(self.get_attr('username')):
            self.set_attr('username', 'sif-user', override=False)
        return True

    def set_attr(self, attr: str, value: Any, override: bool = True) -> bool:
        """Set configuration attribute if not exists, or attribute value should be overrode"""
        if attr not in self.config or (self.config[attr] != value and override):
            self.config[attr] = value
            self.dump()
            return True
        return False
