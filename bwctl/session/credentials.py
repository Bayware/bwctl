"""
This module implements credentials handling
"""

import json
import os
from copy import deepcopy
from typing import List, Dict

import yaml
from bwctl.session.config import Config
from bwctl.utils.common import log_info, log_warn
from bwctl.utils.states import Result


class Credentials:
    """Define credentials object"""

    def __init__(self, fabric: str, state: Dict, config: Config):
        """Initialise all attributes"""
        # Init arguments
        self.credentials: Dict = {
            'aws': {},
            'azr': {},
            'gcp': {},
            'docker': {}
        }
        self.config: Config = config
        self.fabric: str = fabric
        self.state: Dict = state
        # Init expected cloud params and environment variables
        self.params_aws: List = [
            {'env': 'AWS_ACCESS_KEY_ID', 'key': 'aws_access_key_id'},
            {'env': 'AWS_SECRET_ACCESS_KEY', 'key': 'aws_secret_access_key'}
        ]
        self.params_azr: List = [
            {'env': 'AZR_CLIENT_ID', 'key': 'azr_client_id'},
            {'env': 'AZR_CLIENT_SECRET', 'key': 'azr_client_secret'},
            {'env': 'AZR_SUBSCRIPTION_ID', 'key': 'azr_subscription_id'},
            {'env': 'AZR_TENNANT_ID', 'key': 'azr_tennant_id'},
            {'env': 'AZR_RESOURCE_GROUP_NAME', 'key': 'azr_resource_group_name'}
        ]
        self.params_gcp: List = [
            {'env': 'GCP_CREDENTIALS', 'key': 'google_cloud_keyfile_json'},
            {'env': 'GCP_PROJECT_NAME', 'key': 'project_id'}
        ]
        self.params_docker: List = [
            {'key': 'username'},
            {'key': 'password'}
        ]

    def __repr__(self) -> str:
        """"String reputation of an object"""
        return u"{}".format(self.credentials)

    def get_cloud(self, cloud_name: str) -> Result:
        """Get cloud definition from credentials"""
        if cloud_name in self.credentials:
            return Result(True, self.credentials[cloud_name])
        return Result(False, None)

    def get_cloud_param(self, cloud_name: str, param_name: str) -> Result:
        """Get value of param_name from credential's cloud definition"""
        if param_name in self.get_cloud(cloud_name).value:
            if bool(self.credentials[cloud_name][param_name]):
                return Result(True, self.credentials[cloud_name][param_name])
        return Result(False, None)

    def get_aws_param(self, key: str) -> Result:
        """Get AWS param value by key"""
        return self.get_cloud_param('aws', key)

    def set_aws_param(self, key: str, value: str):
        """Set AWS param value by key"""
        self.credentials['aws'][key] = value

    def get_azr_param(self, key: str) -> Result:
        """Get AZR param value by key"""
        return self.get_cloud_param('azr', key)

    def set_azr_param(self, key: str, value: str):
        """Set GCP param value by key"""
        self.credentials['azr'][key] = value

    def get_gcp_param(self, key: str) -> Result:
        """Get GCP param value by key"""
        return self.get_cloud_param('gcp', key)

    def set_gcp_param(self, key: str, value: str):
        """Set GCP param value by key"""
        self.credentials['gcp'][key] = value

    def get_env_aws(self) -> bool:
        """Get AWS credentials from env"""
        credentials_missing: bool = False
        log_info("Checking environment variables: {}".format([x['env'] for x in self.params_aws]))
        for param in self.params_aws:
            env_value: str = os.getenv(param['env'], '')
            if not env_value:
                log_warn("{!r} is not set".format(param['env']))
                credentials_missing = True
            else:
                self.set_aws_param(param['key'], env_value)
        if credentials_missing:
            return False
        log_info("AWS credentials - OK")
        return True

    def get_env_azr(self) -> bool:
        """Get AZR credentials from env"""
        credentials_missing: bool = False
        log_info("Checking environment variables: {}".format([x['env'] for x in self.params_azr]))
        for param in self.params_azr:
            env_value: str = os.getenv(param['env'], '')
            if not env_value:
                log_warn("{!r} is not set".format(param['env']))
                credentials_missing = True
            else:
                self.set_azr_param(param['key'], env_value)
        if credentials_missing:
            return False
        log_info("AZR credentials - OK")
        return True

    def get_env_gcp(self) -> bool:
        """Get GCP credentials from env"""
        credentials_missing: bool = False
        log_info("Checking environment variables: {}".format([x['env'] for x in self.params_gcp]))
        for param in self.params_gcp:
            env_value: str = os.getenv(param['env'], '')
            if not env_value:
                log_warn("{!r} is not set".format(param['env']))
                credentials_missing = True
            else:
                self.set_gcp_param(param['key'], env_value)
        if credentials_missing:
            return False
        log_info("GCP credentials - OK")
        return True

    def check_aws(self) -> bool:
        """Check AWS credentials are provided"""
        credentials_missing: bool = False
        get_cloud: Result = self.get_cloud('aws')
        if get_cloud.status:
            get_param: Result = self.get_aws_param('aws_ec2_role')
            if not get_param.status or not get_param.value:
                log_warn("{!r} is set to 'false'".format('aws_ec2_role'))
                for param in self.params_aws:
                    get_param = self.get_aws_param(param['key'])
                    if not get_param.status:
                        log_warn("{!r} is missing".format(param['key']))
                        credentials_missing = True
            else:
                log_info("AWS credentials - OK (EC2 role is configured)")
                return True
        else:
            log_warn("'aws' section is missing")
            credentials_missing = True
        if credentials_missing:
            return False
        log_info("AWS credentials - OK")
        return True

    def check_azr(self) -> bool:
        """Check AZR credentials are provided"""
        credentials_missing: bool = False
        get_cloud: Result = self.get_cloud('azr')
        if get_cloud.status:
            for param in self.params_azr:
                get_param: Result = self.get_azr_param(param['key'])
                if not get_param.status:
                    log_warn("{!r} is missing".format(param['key']))
                    credentials_missing = True
        else:
            log_warn("'azr' section is missing")
            credentials_missing = True
        if credentials_missing:
            return False
        log_info("AZR credentials - OK")
        return True

    def check_gcp(self) -> bool:
        """Check GCP credentials are provided"""
        credentials_missing: bool = False
        # Check 'google_cloud_keyfile_json'
        get_cloud: Result = self.get_cloud('gcp')
        if get_cloud.status:
            param: Dict = self.params_gcp[0]
            get_param: Result = self.get_gcp_param(param['key'])
            if not get_param.status:
                log_warn("{!r} is missing".format(param['key']))
                credentials_missing = True
            else:
                try:
                    with open(os.path.expanduser(get_param.value), 'r') as cred_f:
                        self.credentials['gcp'] = json.load(cred_f)
                        self.set_gcp_param(param['key'], get_param.value)
                    cred_f.close()
                except FileNotFoundError:
                    log_info("No GCP credentials file found: {!r}".format(get_param.value))
                    credentials_missing = True
            # Check 'project_id'
            param = self.params_gcp[1]
            get_param = self.get_gcp_param(param['key'])
            if not get_param.status:
                log_warn("{!r} is missing".format(param['key']))
                credentials_missing = True
        else:
            log_warn("'gcp' section is missing")
            credentials_missing = True
        if credentials_missing:
            return False
        log_info("GCP credentials - OK")
        return True

    def check_docker(self) -> bool:
        """Check dockerhub credentials are provided"""
        credentials_missing: bool = False
        get_cloud: Result = self.get_cloud('docker')
        if get_cloud.status:
            for param in self.params_docker:
                get_param: Result = self.get_cloud_param('docker', param['key'])
                if not get_param.status:
                    log_warn("{!r} is missing".format(param['key']))
                    credentials_missing = True
        else:
            log_warn("'docker' section is missing")
            credentials_missing = True
        if credentials_missing:
            return False
        log_info("Dockerhub credentials - OK")
        return True

    @staticmethod
    def check_ssh(path: str) -> bool:
        """Checks if SSH key files are exist"""
        private_file_name: str = os.path.expanduser(path)
        public_file_name: str = private_file_name + '.pub'
        log_info("Checking SSH key files:")
        key_failure: bool = False
        if not os.path.isfile(private_file_name):
            log_warn("Private key file is not found: {!r}".format(private_file_name))
            key_failure = True
        else:
            log_info("Private key file exists - OK")
        if not os.path.isfile(public_file_name):
            log_warn("Public key file is not found: {!r}".format(public_file_name))
            key_failure = True
        else:
            log_info("Public key file exists - OK")
        if key_failure:
            log_info("NOTE: If private SSH key is provided as fabric configuration, "
                     "the public part is also expected to exist")
            return False
        return True

    def parse_file(self, path: str) -> bool:
        """Get credentials from file"""
        log_info("Reading credentials file: {!r}".format(path))
        try:
            with open(os.path.expanduser(path), 'r') as cred_f:
                self.credentials = yaml.safe_load(cred_f)
            cred_f.close()
        except FileNotFoundError:
            log_warn("No credentials file found: {!r}".format(path))
            return False
        return True

    def get(self) -> bool:
        """Get all required credentials from file or environment"""
        fabric_credentials = Credentials(self.fabric, self.state, self.config)
        global_credentials = Credentials(self.fabric, self.state, self.config)
        # Check which clounds are required
        clouds: List = ['aws']
        for vpc in self.state['fabric'][self.fabric]['vpc'].items():
            if vpc[1]['cloud'] not in clouds:
                clouds.append(vpc[1]['cloud'])
        log_info('Check if cloud credentials are set for: {!r}'.format(clouds))
        # Parse credentials files that are configured
        no_global_credentials_file: bool = True
        no_fabric_credentials_file: bool = True
        if bool(self.config.get_attr('credentials_file')):
            credentials_file: str = self.config.get_attr('credentials_file')
            log_info('Global credentials file {!r} is configured'.format(credentials_file))
            if not global_credentials.parse_file(credentials_file):
                return False
            no_global_credentials_file = False
        if bool(self.state['fabric'][self.fabric]['config']['credentialsFile']):
            credentials_file = self.state['fabric'][self.fabric]['config']['credentialsFile']
            log_info('Fabric credentials file {!r} is configured'.format(credentials_file))
            if not fabric_credentials.parse_file(credentials_file):
                return False
            no_fabric_credentials_file = False
        if no_global_credentials_file and no_fabric_credentials_file:
            log_info('Credentials files are not configured')
        # Get credentials for all clouds
        for cloud in clouds:
            if cloud == 'aws':
                # Check credentials in fabric file
                if not no_fabric_credentials_file:
                    log_info('Checking fabric credentials for {!r}'.format(cloud))
                    if fabric_credentials.check_aws():
                        self.credentials[cloud] = deepcopy(fabric_credentials.credentials[cloud])
                        continue
                # Check credentials in global file from config
                if not no_global_credentials_file:
                    log_info('Checking global credentials for {!r}'.format(cloud))
                    if global_credentials.check_aws():
                        self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                        continue
                # Check environment variables
                if not global_credentials.get_env_aws():
                    return False
                self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                continue
            elif cloud == 'azr':
                # Check credentials in fabric file
                if not no_fabric_credentials_file:
                    log_info('Checking fabric credentials for {!r}'.format(cloud))
                    if fabric_credentials.check_azr():
                        self.credentials[cloud] = deepcopy(fabric_credentials.credentials[cloud])
                        continue
                # Check credentials in global file from config
                if not no_global_credentials_file:
                    log_info('Checking global credentials for {!r}'.format(cloud))
                    if global_credentials.check_azr():
                        self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                        continue
                # Check environment variables
                if not global_credentials.get_env_azr():
                    return False
                self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                continue
            elif cloud == 'gcp':
                # Check credentials in fabric file
                if not no_fabric_credentials_file:
                    log_info('Checking fabric credentials for {!r}'.format(cloud))
                    if fabric_credentials.check_gcp():
                        self.credentials[cloud] = deepcopy(fabric_credentials.credentials[cloud])
                        continue
                # Check credentials in global file from config
                if not no_global_credentials_file:
                    log_info('Checking global credentials for {!r}'.format(cloud))
                    if global_credentials.check_gcp():
                        self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                        continue
                # Check environment variables
                if not global_credentials.get_env_gcp():
                    return False
                self.credentials[cloud] = deepcopy(global_credentials.credentials[cloud])
                continue
        return True

    def get_aws(self) -> bool:
        """Get S3 state credentials from file"""
        temp_credentials = Credentials(self.fabric, self.state, self.config)
        log_info('Check if credentials are set for S3 repository')
        # Parse global credentials if configured
        no_credentials_file: bool = False
        credentials_file: str = self.config.get_attr('credentials_file')
        if bool(self.config.get_attr('credentials_file')):
            log_info('Global credentials file {!r} is configured'.format(credentials_file))
            if not temp_credentials.parse_file(credentials_file):
                return False
        else:
            log_info('Global credentials file is not configured')
            no_credentials_file = True
        # Check credentials from file
        if not no_credentials_file:
            log_info('Checking global credentials for {!r}'.format('aws'))
            if temp_credentials.check_aws():
                self.credentials['aws'] = deepcopy(temp_credentials.credentials['aws'])
                return True
        # Check environment variables
        if temp_credentials.get_env_aws():
            self.credentials['aws'] = deepcopy(temp_credentials.credentials['aws'])
            return True
        return False

    def get_docker(self) -> bool:
        """Get docker hub credentials from file"""
        global_credentials = Credentials(self.fabric, self.state, self.config)
        fabric_credentials = Credentials(self.fabric, self.state, self.config)
        log_info('Check if credentials are set for Bayware dockerhub registry')
        # Parse credentials files that are configured
        no_global_credentials_file: bool = True
        no_fabric_credentials_file: bool = True
        if bool(self.config.get_attr('credentials_file')):
            credentials_file: str = self.config.get_attr('credentials_file')
            log_info('Global credentials file {!r} is configured'.format(credentials_file))
            if not global_credentials.parse_file(credentials_file):
                return False
            no_global_credentials_file = False
        if bool(self.state['fabric'][self.fabric]['config']['credentialsFile']):
            credentials_file = self.state['fabric'][self.fabric]['config']['credentialsFile']
            log_info('Fabric credentials file {!r} is configured'.format(credentials_file))
            if not fabric_credentials.parse_file(credentials_file):
                return False
            no_fabric_credentials_file = False
        if no_global_credentials_file and no_fabric_credentials_file:
            log_info('Credentials files are not configured')
        # Check credentials in fabric file
        if not no_fabric_credentials_file:
            log_info('Checking fabric credentials for {!r}'.format('Bayware dockerhub'))
            if fabric_credentials.check_docker():
                self.credentials['docker'] = deepcopy(fabric_credentials.credentials['docker'])
                return True
        # Check credentials in global file from config
        if not no_global_credentials_file:
            log_info('Checking global credentials for {!r}'.format('Bayware dockerhub'))
            if global_credentials.check_docker():
                self.credentials['docker'] = deepcopy(global_credentials.credentials['docker'])
                return True
        return False
