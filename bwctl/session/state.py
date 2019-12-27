"""
This module implements state handling
"""

import os
import secrets
import string
import sys
from copy import deepcopy
from typing import Any, List, Dict, Tuple

import boto3
import bwctl_resources.ansible
import yaml
from bwctl.actions.ansible import Ansible
from bwctl.actions.terraform import Terraform
from bwctl.session.config import Config
from bwctl.session.credentials import Credentials
from bwctl.utils.common import dump_dict_to_file, dump_dict_to_s3, log_info, log_ok, log_warn, log_error
from bwctl.utils.states import ObjectStatus, ObjectState, ObjectKind, Result


class State:
    """Define state object"""

    def __init__(self, version: str, version_family: str):
        """Initialise all attributes"""
        # Initialise bwctl version
        self.api_version: str = 'fabric.bayware.io/v2'
        self.version: str = version
        self.version_family: str = version_family

        # Init configuration
        self.config = Config(self.version, self.version_family)
        self.config.init()

        # File names
        self.local_state_file: str = os.path.join(self.config.dir, 'state')
        self.ansible_dir: str = os.path.dirname(bwctl_resources.ansible.__file__)
        self.state_file: str = ''
        self.state: Dict = {}

        # Initialise supported object states
        self.object_state = ObjectState
        self.object_status = ObjectStatus

    def __repr__(self) -> str:
        """"String reputation of an object"""
        return u"{}".format(self.state)

    def _check_state_attr_value(self, fabric: str, attr: str, value: str) -> bool:
        """Returns True if value exists in attr for given fabric, False otherwise"""
        return bool(self.state['fabric'][fabric][attr].get(value))

    def check_fabric(self, name: str) -> bool:
        """Return True if fabric exists, False otherwise"""
        return bool(self.state['fabric'].get(name))

    def check_vpc(self, fabric: str, name: str) -> bool:
        """Return True if VPC exists, False otherwise"""
        return self._check_state_attr_value(fabric, 'vpc', name)

    def check_nodebatch(self, name: str) -> bool:
        """Return True if nodebatch exists in state, False otherwise"""
        if name in self.state['batch']:
            return True
        else:
            return False

    def check_nodeobj(self, fabric: str, name: str, objectkind: ObjectKind) -> bool:
        """Calls properly procedure in case ob object_kind"""
        if objectkind == ObjectKind.PROCESSOR:
            return self.check_processor(fabric, name)
        elif objectkind == ObjectKind.WORKLOAD:
            return self.check_workload(fabric, name)
        elif objectkind == ObjectKind.ORCHESTRATOR:
            return self.check_orchestrator(fabric, name)
        return False

    def check_orchestrator(self, fabric: str, name: str) -> bool:
        """Return True if orchestrator exists, False otherwise"""
        return self._check_state_attr_value(fabric, ObjectKind.ORCHESTRATOR.value, name)

    def check_processor(self, fabric: str, name: str) -> bool:
        """Return True if processor exists, False otherwise"""
        return self._check_state_attr_value(fabric, ObjectKind.PROCESSOR.value, name)

    def check_workload(self, fabric: str, name: str) -> bool:
        """Return True if workload exists, False otherwise"""
        return self._check_state_attr_value(fabric, ObjectKind.WORKLOAD.value, name)

    def get_nodebatch(self, name: str) -> Dict:
        """Return nodebatch obj from state"""
        return self.state[ObjectKind.BATCH.value].get(name)

    def get_fabric(self, name: str) -> Dict:
        """Return fabric obj from state"""
        return self.state[ObjectKind.FABRIC.value].get(name)

    def get_fabric_objects(self, obj_kind: str, fabric_name: str = None) -> Dict:
        """Return fabric's objects of provided kind"""
        if fabric_name is None:
            fabric_name = self.get_current_fabric()
        return self.get_fabric(fabric_name).get(obj_kind, {})

    def get_fabric_object(self, obj_kind: str, obj_name: str, fabric_name: str = None) -> Dict:
        """Return fabric's object by name of provided kind"""
        if fabric_name is None:
            fabric_name = self.get_current_fabric()
        return self.get_fabric_objects(obj_kind, fabric_name).get(obj_name, {})

    def delete_nodebatch(self, name: str) -> Result:
        """Delete nodebatch obj from state"""
        try:
            del (self.state[ObjectKind.BATCH.value][name])
        except NameError as del_err:
            return Result(False, del_err)
        return Result(True)

    def delete_fabric(self, name: str) -> Result:
        """Delete fabric obj from state"""
        try:
            del (self.state[ObjectKind.FABRIC.value][name])
        except NameError as del_err:
            return Result(False, del_err)
        return Result(True)

    def delete_fabric_object(self, obj_kind: str, obj_name: str, fabric_name: str = None) -> Result:
        if fabric_name is None:
            fabric_name = self.get_current_fabric()
        try:
            del (self.state['fabric'][fabric_name][obj_kind][obj_name])
        except NameError as del_err:
            return Result(False, del_err)
        return Result(True)

    def dump(self) -> bool:
        """Dump state to a file"""
        cloud_storage_cfg: Dict = self.config.get_attr('cloud_storage')
        if cloud_storage_cfg['state']['enabled']:
            s3_state_url: str =\
                'https://' + cloud_storage_cfg['state']['bucket'] + '.s3-' + \
                cloud_storage_cfg['state']['region'] + '.amazonaws.com/' + self.state_file
            log_info('Uploading state: {!r}'.format(s3_state_url))
            credentials = Credentials(self.get_current_fabric(), self.state, self.config)
            if not credentials.get_aws():
                log_error('Cannot dump state to S3. Not able to get credentials')
                return False
            return dump_dict_to_s3(self.state, cloud_storage_cfg['state']['bucket'], self.state_file,
                                   credentials)
        else:
            return dump_dict_to_file(self.state_file, self.state)

    def get_current_fabric(self) -> Any:
        """Get current fabric name"""
        current_fabric: str = self.config.get_current_fabric()
        if self.check_fabric(current_fabric):
            if (self.check_object_state(self.state['fabric'][current_fabric], ObjectState.CONFIGURED)
                    and self.check_object_status(self.state['fabric'][current_fabric], ObjectStatus.SUCCESS)) \
                    or self.check_object_state(self.state['fabric'][current_fabric], ObjectState.DELETING):
                return current_fabric
        else:
            return None

    def get(self) -> Dict:
        """Get application state"""
        return self.state

    def get_ssh_key(self, fabric: str = None) -> Any:
        """Get fabric ssh key name"""
        if fabric is None:
            fabric = self.get_current_fabric()
        if fabric and fabric in self.state['fabric']:
            if 'privateKey' in self.state['fabric'][fabric]['config']['sshKeys']:
                if bool(self.state['fabric'][fabric]['config']['sshKeys']['privateKey']):
                    return self.state['fabric'][fabric]['config']['sshKeys']['privateKey']
                else:
                    return os.path.join(self.config.dir, fabric, "ssh_key")
            else:
                return os.path.join(self.config.dir, fabric, "ssh_key")
        else:
            return False

    def get_ssh_pub_key(self, fabric: str = None) -> Any:
        """Get fabric ssh pub key name"""
        if fabric is None:
            fabric = self.get_current_fabric()
        if fabric and fabric in self.state['fabric']:
            if 'privateKey' in self.state['fabric'][fabric]['config']['sshKeys']:
                if bool(self.state['fabric'][fabric]['config']['sshKeys']['privateKey']):
                    return self.state['fabric'][fabric]['config']['sshKeys']['privateKey'] + '.pub'
                else:
                    return os.path.join(self.config.dir, fabric, "ssh_key.pub")
            else:
                return os.path.join(self.config.dir, fabric, "ssh_key.pub")
        else:
            return False

    def set_ssh_key(self, path: str, fabric: str = None) -> bool:
        """Set fabric ssh key configuration"""
        if fabric is None:
            fabric = self.get_current_fabric()
        if fabric:
            self.state['fabric'][fabric]['config']['sshKeys']['privateKey'] = path
        return True

    def check(self, state_file: str) -> bool:
        """Check state for API version compatibility"""
        if 'apiVersion' in self.state:
            if self.state['apiVersion'] != self.api_version:
                log_warn("WARNING: bwctl state incompatibility found. State API version {!r} loaded from file {!r} "
                         "doesn't correspond current bwctl API version {!r}. Please check state file structure and "
                         "modify it according to the current API version structure to make bwctl working as expected"
                         .format(self.state['apiVersion'], state_file, self.api_version))
        if 'batch' not in self.state:
            self.state['batch'] = {}
        if 'fabric' not in self.state:
            self.state['fabric'] = {}
        # Make sure node properties are present for nodes
        state_changed_list: List = []
        state_changed: bool = False
        for fabric in self.state['fabric']:
            for obj_kind in [ObjectKind.ORCHESTRATOR.value, ObjectKind.PROCESSOR.value, ObjectKind.WORKLOAD.value]:
                for obj_key in self.state['fabric'][fabric][obj_kind]:
                    obj_val: Dict = self.state['fabric'][fabric][obj_kind][obj_key]
                    if 'properties' not in obj_val:
                        obj_val['properties'] = {}
                    if 'marketplace' not in obj_val['properties']:
                        obj_val['properties']['marketplace'] = self.config.get_attr('marketplace')
                        if 'marketplace' not in state_changed_list:
                            state_changed_list.append('marketplace')
                            state_changed = True
        if state_changed:
            log_warn("WARNING: bwctl state incompatibility found. State objects are missing required properties: {}. "
                     "Properties are added with default values and going to be saved on the first upcoming dump "
                     "operation".format(state_changed_list))
        return True

    def init(self) -> bool:
        """Init state"""
        self.state_file = self.local_state_file
        self.state['apiVersion'] = self.api_version
        self.state['batch'] = {}
        self.state['fabric'] = {}
        cloud_storage_cfg: Dict = self.config.get_attr('cloud_storage')
        if cloud_storage_cfg['state']['enabled']:
            self.state_file = self.config.get_attr('fabric_manager')['id'] + '/state'
            log_info('Getting state from S3')
            credentials = Credentials(self.get_current_fabric(), self.state, self.config)
            if not credentials.get_aws():
                log_error('Cannot download state from S3. Not able to get credentials')
                return False
            s3_client = \
                boto3.client('s3', aws_access_key_id=credentials.get_aws_param('aws_access_key_id').value,
                             aws_secret_access_key=credentials.get_aws_param('aws_secret_access_key').value)
            try:
                response = s3_client.get_object(Bucket=cloud_storage_cfg['state']['bucket'], Key=self.state_file)
                self.state = yaml.safe_load(response["Body"])
                log_ok("State downloaded successfully")
                self.check(cloud_storage_cfg['state']['bucket'] + '/' + self.state_file)
            except s3_client.exceptions.ClientError as dump_err:
                if 'NoSuchKey' in str(dump_err):
                    # Check if local state exist
                    try:
                        with open(self.local_state_file, 'r') as state_f:
                            self.state = yaml.safe_load(state_f)
                            self.check(self.local_state_file)
                        state_f.close()
                        log_warn("State file is missing on S3, local state file {!r} going to be uploaded".format(
                            self.local_state_file))
                        self.dump()
                    except FileNotFoundError:
                        log_info("No state file found, starting clean")
                        self.dump()
                else:
                    log_error("S3 error: {}".format(dump_err))
                    sys.exit(1)
        else:
            try:
                with open(self.state_file, 'r') as state_f:
                    self.state = yaml.safe_load(state_f)
                    self.check(self.state_file)
                state_f.close()
            except FileNotFoundError:
                log_info("No state file found, starting clean")
                self.dump()
        return True

    @staticmethod
    def normalise_string(input_string: str) -> str:
        """Normalise string"""
        # TODO: Add actual normalisation
        return str(input_string).lower()

    def normalise_state_obj_name(self, obj: str, name: str) -> str:
        """Normalise state object name"""
        norm_name: str = self.normalise_string(name)
        if name != norm_name:
            log_warn('Normalising {0} name from {1!r} to {2!r}'.format(obj, name, norm_name))
        return norm_name

    def check_object_state(self, obj: Dict, state: Any) -> bool:
        """ Returns true if current state of obj is in <state>, false otherwise"""

        def check_list_object_state(state_list: Any) -> bool:
            """ Check if values in state_list is actually list, and all elements is valid ObjectState values"""
            return bool(state_list) and type(state_list) == list and all(isinstance(elem, ObjectState)
                                                                         for elem in state_list)

        if type(state) == ObjectState:
            return self.get_object_state(obj) == state
        elif check_list_object_state(state):
            return self.get_object_state(obj) in state
        else:
            return False

    def check_object_state_status(self, obj: Dict, state: ObjectState, status: ObjectStatus) -> bool:
        """Return True if Obj current state/status is given state/status"""
        return self.get_object_state(obj) == state and self.get_object_status(obj) == status

    def check_object_status(self, obj: Dict, status: ObjectStatus) -> bool:
        """Return True if Obj current status is given status"""
        return self.get_object_status(obj) == status

    def set_object_state_status(self, obj: Dict, state: ObjectState, status: ObjectStatus):
        """Set Object state and status tuple"""
        self.set_object_state(obj, state)
        self.set_object_status(obj, status)

    def set_object_state(self, obj: Dict, state: ObjectState) -> bool:
        """Set obj[state] if state valid, returns false if invalid"""
        try:
            if self.object_state.has_value(state.value):
                obj['state'] = state.value
            else:
                log_error("Invalid state {0!r}".format(state))
                return False
        except ValueError:
            log_error("Invalid state {0!r}".format(state))
            return False
        except AttributeError:
            log_error("Invalid state {0!r}".format(state))
            return False
        return True

    @staticmethod
    def get_object_state(obj: Dict) -> Any:
        """Returns state of given obj"""
        try:
            return ObjectState(obj['state'])
        except TypeError:
            log_error("No state in Obj")
            return False
        except ValueError:
            return None

    def set_object_status(self, obj: Dict, status: ObjectStatus) -> bool:
        """Set obj[status] if status valid, returns false if invalid"""
        try:
            if self.object_status.has_value(status.value):
                obj['status'] = status.value
            else:
                log_error("Invalid status {0!r}".format(status))
                return False
        except ValueError:
            log_error("Invalid status {0!r}".format(status))
            return False
        except AttributeError:
            log_error("Invalid status {0!r}".format(status))
            return False
        return True

    @staticmethod
    def get_object_status(obj: Dict) -> Any:
        """Returns status of given obj"""
        try:
            return ObjectStatus(obj['status'])
        except TypeError:
            log_error("No status in Obj")
            return False
        except ValueError:
            return None

    def add_batch(self, batch_name: str, batch: Dict):
        """Adds batch obj to the state"""
        self.state['batch'][batch_name] = batch

    def add_batch_obj(self, batch_name: str, obj_type: str, obj_name: str, obj: Dict):
        """Adds state batch obj to the batch"""
        if obj_type not in self.state['batch'][batch_name]:
            self.state['batch'][batch_name][obj_type] = {}
        self.state['batch'][batch_name][obj_type][obj_name] = obj

    def add_fabric(self, fabric_name: str, fabric: Dict):
        """Adds fabric obj to the state"""
        self.state['fabric'][fabric_name] = fabric

    def add_fabric_obj(self, fabric_name: str, obj_type: str, obj_name: str, obj: Dict):
        """Adds state obj to the fabric"""
        self.state['fabric'][fabric_name][obj_type][obj_name] = deepcopy(obj)

    @staticmethod
    def get_clean_fabric() -> Dict:
        """Returns clean fabric state object"""
        return {
            'config': {
                'companyName': {},
                'credentialsFile': {},
                'sshKeys': {
                    'privateKey': {}
                }
            },
            'orchestrator': {},
            'processor': {},
            'state': {},
            'status': {},
            'vpc': {},
            'workload': {}
        }

    @staticmethod
    def get_clean_vpc() -> Dict:
        """Returns clean vpc state object"""
        return {
            'cloud': {},
            'region': {},
            'index': {},
            'properties': {},
            'state': {},
            'status': {}
        }

    def get_clean_nodeobj(self, objectkind: ObjectKind) -> Dict:
        """Calls properly procedure in case of object_kind"""
        if objectkind == ObjectKind.PROCESSOR:
            return self.get_clean_processor()
        elif objectkind == ObjectKind.WORKLOAD:
            return self.get_clean_workload()
        elif objectkind == ObjectKind.ORCHESTRATOR:
            return self.get_clean_orchestrator()
        return {}

    def get_clean_orchestrator(self) -> Dict:
        """Returns clean orchestrator state object"""
        return {
            'index': {},
            'properties': {
                'marketplace': self.config.get_attr('marketplace')
            },
            'role': {},
            'state': {},
            'status': {},
            'type': {},
            'vpc': {}
        }

    def get_clean_processor(self) -> Dict:
        """Returns clean processor state object"""
        return {
            'index': {},
            'config': {
                'orchestrator': {}
            },
            'properties': {
                'marketplace': self.config.get_attr('marketplace')
            },
            'state': {},
            'status': {},
            'vpc': {}
        }

    def get_clean_workload(self) -> Dict:
        """Returns clean workload state object"""
        return {
            'index': {},
            'config': {
                'orchestrator': {}
            },
            'properties': {
                'marketplace': self.config.get_attr('marketplace'),
                'os_type': self.config.get_attr('os_type')
            },
            'state': {},
            'status': {},
            'vpc': {}
        }

    @staticmethod
    def get_passwd() -> str:
        """Generates password"""
        charset: str = string.ascii_letters + string.digits
        passwd: str = ''.join(secrets.choice(charset) for _ in range(12))
        return passwd

    @staticmethod
    def show_passwd(passwd: str, orchestrator_type: str):
        """Shows password"""
        log_warn("IMPORTANT: Here is {}'s admin password that was used during setup. Please change it after first login"
                 .format(orchestrator_type))
        log_info("Password: {0}".format(passwd))

    def fabric_configure(self, fabric_name: str, skip_ssh: bool = False) -> Tuple:
        """Configure fabric (ansible)"""
        ansible_playbook_ca: str = "configure-fabric-ca.yml"
        ansible_playbook_ssh: str = "configure-fabric-ssh-key.yml"
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        self.set_object_state_status(self.state['fabric'][fabric_name], ObjectState.CONFIGURED, ObjectStatus.SUCCESS)
        log_info("Install CA for fabric {0!r}".format(fabric_name))
        ansible_result: Tuple = ansible.run_playbook(ansible_playbook_ca, local=True)
        if not ansible_result[0]:
            log_warn('Cannot install CA. There is issue with ansible playbook execution')
            self.set_object_state_status(self.state['fabric'][fabric_name], ObjectState.CONFIGURED, ObjectStatus.FAILED)
            return False, ansible_result[1]
        if not skip_ssh:
            log_info("Install SSH keys for fabric {0!r}".format(fabric_name))
            ansible_result = ansible.run_playbook(ansible_playbook_ssh, local=True)
            if not ansible_result[0]:
                log_warn('Cannot install SSH key. There is issue with ansible playbook execution')
                self.set_object_state_status(self.state['fabric'][fabric_name], ObjectState.CONFIGURED,
                                             ObjectStatus.FAILED)
                return False, ansible_result[1]
        return True, 0

    def fabric_create(self, fabric_name: str) -> Tuple:
        """Create fabric (ansible)"""
        ansible_playbook: str = "create-fabric.yml"
        ansible = Ansible(self, fabric_name)
        self.set_object_state_status(self.state['fabric'][fabric_name], ObjectState.CREATED, ObjectStatus.SUCCESS)
        log_info("Create resources for fabric {0!r}".format(fabric_name))
        ansible_result: Tuple = ansible.run_playbook(ansible_playbook, local=True)
        if not ansible_result[0]:
            log_warn('Cannot create resources. There is issue with ansible playbook execution')
            self.set_object_state_status(self.state['fabric'][fabric_name], ObjectState.CREATED, ObjectStatus.FAILED)
            return False, ansible_result[1]
        return True, 0

    def obj_create_check(self, fabric_name: str, obj_list: Dict) -> bool:
        """Performs creation checks before actual creation actions"""
        # Check if there are ssh proxy for workloads
        failure_in_batch: bool = False
        if ObjectKind.WORKLOAD in obj_list:
            for obj_name in obj_list[ObjectKind.WORKLOAD]:
                obj_vpc = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][obj_name]['vpc']
                all_proc = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                            x[1]['vpc'] == obj_vpc]
                if not bool(all_proc):
                    log_error(
                        "Cannot created workload {!r}. At least one processor should be present in VPC {!r}".format(
                            obj_name, obj_vpc))
                    failure_in_batch = True
        if failure_in_batch:
            return False
        return True

    def obj_create(self, fabric_name: str, obj_list: List, credentials: Credentials) -> Tuple:
        """Creates object (orchestrator/processor/workload) from state (terraform and ansible)"""
        terraform = Terraform(fabric_name, self, credentials, self.version)
        if not terraform.plan_generate():
            for obj_kind in obj_list:
                for obj_name in obj_list[obj_kind]:
                    log_error("Cannot create {0}s: {1!r}. There is issue with terraform plan generation".
                              format(obj_kind.value, obj_name))
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
            return False, 1
        terraform_result: Tuple = terraform.plan_execute()
        if not terraform_result[0]:
            for obj_kind in obj_list:
                for obj_name in obj_list[obj_kind]:
                    log_error("Cannot create {0}s: {1!r}. There is issue with terraform plan execution".
                              format(obj_kind.value, obj_name))
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
            return False, terraform_result[1]
        # Get IP addresses
        failure_in_batch: bool = False
        for obj_kind in obj_list:
            for obj_name in obj_list[obj_kind]:
                output_var: str = 'public_ip'
                if obj_kind is ObjectKind.WORKLOAD:
                    output_var = 'private_ip'
                ip_addr: str = terraform.get_output_variable_with_retries(obj_name, output_var, 10)
                self.state['fabric'][fabric_name][obj_kind.value][obj_name]['properties']['ip'] = ip_addr
                if ip_addr is None:
                    log_error("{0} {1!r} created with problems: IP address is missing".format(obj_kind.value,
                                                                                              obj_name))
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
                    failure_in_batch = True
        if failure_in_batch:
            return False, 1
        # If dns was not enabled - than enable it
        # String expr
        for obj_kind in obj_list:
            for obj_name in obj_list[obj_kind]:
                if self.state['fabric'][fabric_name][obj_kind.value][obj_name]['properties']['dns_enabled'] == 'false':
                    self.state['fabric'][fabric_name][obj_kind.value][obj_name]['properties']['dns_enabled'] = 'true'

        log_info("Creating DNS records...")
        # Re-initialize TF object instance to update state in terraform module:
        terraform = Terraform(fabric_name, self, credentials, self.version)
        if not terraform.plan_generate():
            log_error('Cannot create DNS. There is issue with terraform plan generation')
            for obj_kind in obj_list:
                for obj_name in obj_list[obj_kind]:
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
            return False, 1
        terraform_result = terraform.plan_execute()
        if not terraform_result[0]:
            log_error('Cannot create DNS. There is issue with terraform plan execution')
            for obj_kind in obj_list:
                for obj_name in obj_list[obj_kind]:
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
            return False, terraform_result[1]
        # Get fqdn
        for obj_kind in obj_list:
            for obj_name in obj_list[obj_kind]:
                obj_fqdn: str = terraform.get_output_variable_with_retries(obj_name + '-dns', 'fqdn', 10)
                self.state['fabric'][fabric_name][obj_kind.value][obj_name]['properties']['fqdn'] = obj_fqdn
                if obj_fqdn is None:
                    log_error("{0} {1!r} created with problems: FQDN is missing".format(obj_kind.value, obj_name))
                    self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                 ObjectState.CREATED, ObjectStatus.FAILED)
                    failure_in_batch = True
        if failure_in_batch:
            return False, 1
        # Get processors to be workload's ssh proxy
        ansible_node_vars: Dict = {}
        for obj_kind in obj_list:
            if obj_kind == ObjectKind.WORKLOAD:
                for obj_name in obj_list[obj_kind]:
                    ansible_node_vars[obj_name] = []
                    obj_vpc: Dict = self.state['fabric'][fabric_name][obj_kind.value][obj_name]['vpc']
                    all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items()
                                      if x[1]['vpc'] == obj_vpc]
                    success_proc: List = [x for x in self.state['fabric'][fabric_name][
                                          ObjectKind.PROCESSOR.value].items() if x[1]['vpc'] == obj_vpc and
                                          self.check_object_status(x[1], ObjectStatus.SUCCESS)]
                    if bool(all_proc):
                        # If there success created processors use it
                        if bool(success_proc):
                            ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                                'ip': success_proc[0][1]['properties']['ip']}))
                        else:  # Use any otherwise
                            ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                                'ip': all_proc[0][1]['properties']['ip']}))
                    else:
                        log_error("Cannot provision workload {!r}. At least one processor should be present in VPC \
                                  {!r}".format(obj_name, obj_vpc))
                        failure_in_batch = True
        if failure_in_batch:
            return False, 1
        # Check if reachable and ssh available
        ansible_err_code: int = 0
        for obj_kind in obj_list:
            for obj_name in obj_list[obj_kind]:
                log_info("Checking if node {0!r} is accessible...".format(obj_name))
                ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
                nodes_list: List = [obj_name]
                if obj_kind == ObjectKind.WORKLOAD:
                    nodes_list.append([x[1]['name'] for x in ansible_node_vars[obj_name] if 'ssh_proxy_host' in
                                      x[0]][0])
                if not ansible.inventory_generate(nodes_list, per_node_vars=ansible_node_vars):
                    failure_in_batch = True
                    ansible_err_code = 1
                else:
                    ansible_result: Tuple = ansible.run_playbook("check-node-online.yml")
                    if not ansible_result[0]:
                        self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                     ObjectState.CREATED, ObjectStatus.FAILED)
                        log_error("Node {0!r} is unreachable".format(obj_name))
                        self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                     ObjectState.CREATED, ObjectStatus.FAILED)
                        failure_in_batch = True
                        ansible_err_code = ansible_result[1]
        if failure_in_batch:
            return False, ansible_err_code
        # Run Ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        nodes_list = []
        for obj_kind in obj_list:
            nodes_list = nodes_list + obj_list[obj_kind]
        if not ansible.inventory_generate(nodes_list, per_node_vars=ansible_node_vars):
            failure_in_batch = True
            ansible_err_code = 1
        else:
            ansible_result = ansible.run_playbook("create-node.yml")
            if not ansible_result[0]:
                for obj_kind in obj_list:
                    for obj_name in obj_list[obj_kind]:
                        self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                     ObjectState.CREATED, ObjectStatus.FAILED)
                log_error("{0!r} created with problems: Ansible playbook failed".format(nodes_list))
                failure_in_batch = True
                ansible_err_code = ansible_result[1]
            else:
                for obj_kind in obj_list:
                    for obj_name in obj_list[obj_kind]:
                        self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind.value][obj_name],
                                                     ObjectState.CREATED, ObjectStatus.SUCCESS)
                log_ok("{0!r} created successfully".format(nodes_list))
        if failure_in_batch:
            return False, ansible_err_code
        # Success
        return True, 0

    def orchestrator_configure(self, fabric_name: str, orchestrator_list: List,
                               orch_state: ObjectState = ObjectState.CONFIGURED, controller_passwd: str = None,
                               grafana_passwd: str = None, credentials: Credentials = None) -> Tuple:
        """Configure orchestrator entities from state (ansible)"""
        # Init ansible inventory
        obj_kind: str = ObjectKind.ORCHESTRATOR.value
        ansible_nodes: List = orchestrator_list[:]
        for orchestrator in orchestrator_list:
            orch: Dict = self.state['fabric'][fabric_name][obj_kind][orchestrator]
            if self.check_object_status(orch, ObjectStatus.FAILED) \
                    and self.check_object_state(orch, ObjectState.CREATED):
                log_error("Cannot configure, {0} {1!r} in failed state".format(obj_kind, orchestrator))
                return False, 1
        ansible_vars: List = []
        ansible_node_vars: Dict = {}
        ansible_playbook_name: str = 'configure-orchestrator.yml'
        # Get branch and family version
        ansible_vars.append(('env_repo_branch', self.config.get_branch()))
        ansible_vars.append(('env_family_version', self.config.get_family()))
        # Check if production mode
        if self.config.get_attr('production'):
            fabric_manager: Dict = self.config.get_attr('fabric_manager')
            ansible_vars.append(('env_ssh_src_address', fabric_manager['ip']))
        # Check if there is swarm manager
        manager: List = [x for x in self.state['fabric'][fabric_name][obj_kind].items() if 'manager' in x[1]['role']]
        manager_found: bool = False
        if not bool(manager):
            for orch in orchestrator_list:
                obj: Dict = self.state['fabric'][fabric_name][obj_kind][orch]
                if obj['type'] == 'controller':
                    obj['role'] = 'manager'
                    manager_found = True
                else:
                    obj['role'] = 'worker'
        else:
            manager_found = True
        if not manager_found:
            log_error("Cannot configure {}. Controller should be present in node list to be swarm manager".format(
                obj_kind.title()))
            return False, 1
        manager = [x for x in self.state['fabric'][fabric_name][obj_kind].items() if 'manager' in x[1]['role']]
        if bool(manager):
            ansible_vars.append(('env_swarm_manager_host', manager[0][0]))
            if manager[0][0] not in ansible_nodes:
                ansible_nodes.append(manager[0][0])
                ansible_vars.append(('env_swarm_manager_only', True))
        # Check if controller passwd is provided
        if controller_passwd is not None:
            ansible_vars.append(('env_controller_passwd', controller_passwd))
        # Check if grafana passwd is provided
        if grafana_passwd is not None:
            ansible_vars.append(('env_grafana_passwd', grafana_passwd))
        # Ansible execution to setup swarm manager
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        log_info("Setup/check swarm manager on {0} {1!r}".format(obj_kind, manager[0][0]))
        if not ansible.inventory_generate([manager[0][0]], ansible_vars):
            return False, 1
        ansible_result: Tuple = ansible.run_playbook('install-swarm-manager.yml')
        if not ansible_result[0]:
            log_error('Cannot configure {0}. Not able to setup/check swarm manager'.format(obj_kind))
            return False, ansible_result[1]
        # Get processors to be ssh proxy, if there are workloads
        for obj_name in self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value]:
            ansible_node_vars[obj_name] = []
            obj_vpc: List = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][obj_name]['vpc']
            all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                              x[1]['vpc'] == obj_vpc]
            success_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                                  x[1]['vpc'] == obj_vpc and self.check_object_status(x[1], ObjectStatus.SUCCESS)]
            if bool(all_proc):
                # If there success created processors use it
                if bool(success_proc):
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                                           'ip': success_proc[0][1]
                                                                           ['properties']['ip']}))
                else:  # Use any otherwise
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                                           'ip': all_proc[0][1]['properties']['ip']}))
            else:
                log_warn("Workload {!r} wont be reachable. At least one processor should be present in VPC {!r}"
                         .format(obj_name, obj_vpc))
        # Get dockerhub creadentials
        if credentials is not None:
            ansible_vars.append(('env_dockerhub_username', credentials.get_cloud_param('docker', 'username').value))
            ansible_vars.append(('env_dockerhub_password', credentials.get_cloud_param('docker', 'password').value))
        # Ansible execution to configure orchestrator
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        log_info("Configure {0}: {1!r}".format(obj_kind, orchestrator_list))
        if not ansible.inventory_generate(ansible_nodes, node_vars=ansible_vars, per_node_vars=ansible_node_vars):
            return False, 1
        ansible_result = ansible.run_playbook(ansible_playbook_name)
        if not ansible_result[0]:
            for orchestrator in orchestrator_list:
                self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind][orchestrator], orch_state,
                                             ObjectStatus.FAILED)
            log_error('Install orchestrator failed. There is issue with ansible playbook execution')
            return False, ansible_result[1]
        # Success
        for orchestrator in orchestrator_list:
            self.set_object_state_status(self.state['fabric'][fabric_name][obj_kind][orchestrator], orch_state,
                                         ObjectStatus.SUCCESS)
        log_ok("{0}s: {1!r} configured successfully".format(obj_kind.title(), orchestrator_list))
        return True, 0

    def workload_configure(self, fabric_name: str, workload_list: List) -> Tuple:
        """Configure workloads"""
        # Initialize ansible inventory
        ansible_vars: List = []
        ansible_node_vars: Dict = {}
        ansible_nodes: List = workload_list[:]
        ansible_playbook: str = "configure-workload.yml"
        # Get branch and family version
        ansible_vars.append(('env_repo_branch', self.config.get_branch()))
        ansible_vars.append(('env_family_version', self.config.get_family()))
        for workload_name in workload_list:
            # Get configuration from state
            ansible_node_vars[workload_name] = []
            for x in self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]['config'].items():
                ansible_node_vars[workload_name].append(('env_workload_' + x[0], x[1]))
            # Get processors to be workload's ssh proxy
            obj_vpc: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]['vpc']
            all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                              x[1]['vpc'] == obj_vpc]
            success_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                                  x[1]['vpc'] == obj_vpc and self.check_object_status(x[1], ObjectStatus.SUCCESS)]
            if bool(all_proc):
                # If there success created processors use it
                if bool(success_proc):
                    ansible_node_vars[workload_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                             'ip': success_proc[0][1]['properties']['ip']}))
                else:  # Use any otherwise
                    ansible_node_vars[workload_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                             'ip': all_proc[0][1]['properties']['ip']}))
            else:
                log_error("Cannot provision workload {!r}. At least one processor should be present in VPC \
                            {!r}".format(workload_name, obj_vpc))
                return False, 1
        # Check if production mode
        if self.config.get_attr('production'):
            fabric_manager: Dict = self.config.get_attr('fabric_manager')
            ansible_vars.append(('env_ssh_src_address', fabric_manager['ip']))
            ansible_vars.append(('env_production_mode', self.config.get_attr('production')))
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if not ansible.inventory_generate(ansible_nodes, node_vars=ansible_vars, per_node_vars=ansible_node_vars):
            return False, 1
        ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
        if not ansible_result[0]:
            log_error('Cannot configure workload. There is issue with ansible playbook execution')
            for workload_name in workload_list:
                obj: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                self.set_object_state_status(obj, ObjectState.CONFIGURED, ObjectStatus.FAILED)
            return False, ansible_result[1]
        for workload_name in workload_list:
            obj = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
            self.set_object_state_status(obj, ObjectState.CONFIGURED, ObjectStatus.SUCCESS)
        log_ok("Workloads {0!r} configured successfully".format(workload_list))
        return True, 0

    def processor_configure(self, fabric_name: str, processor_list: List) -> Tuple:
        """Configure processors"""
        # Initialize ansible inventory
        ansible_vars: List = []
        ansible_node_vars: Dict = {}
        ansible_nodes: List = processor_list[:]
        ansible_playbook: str = "configure-processor.yml"
        # Get branch and family version
        ansible_vars.append(('env_repo_branch', self.config.get_branch()))
        ansible_vars.append(('env_family_version', self.config.get_family()))
        for processor_name in processor_list:
            ansible_node_vars[processor_name] = []
            for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]['config'].items():
                ansible_node_vars[processor_name].append(('env_processor_' + x[0], x[1]))
        # Check if production mode
        if self.config.get_attr('production'):
            fabric_manager: Dict = self.config.get_attr('fabric_manager')
            ansible_vars.append(('env_ssh_src_address', fabric_manager['ip']))
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if not ansible.inventory_generate(ansible_nodes, node_vars=ansible_vars, per_node_vars=ansible_node_vars):
            return False, 1
        ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
        if not ansible_result[0]:
            log_error('Cannot configure processor. There is issue with ansible playbook execution')
            for processor_name in processor_list:
                obj: Dict = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                self.set_object_state_status(obj, ObjectState.CONFIGURED, ObjectStatus.FAILED)
            return False, ansible_result[1]
        # Success
        for processor_name in processor_list:
            obj = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
            self.set_object_state_status(obj, ObjectState.CONFIGURED, ObjectStatus.SUCCESS)
        log_ok("Processors {0!r} configured successfully".format(processor_list))
        return True, 0

    def obj_update(self, ansible_playbook: str, obj_type: str, obj_list: List,
                   ansible_vars: List = None) -> Tuple:
        """Update object"""
        ansible_nodes: List = obj_list[:]
        ansible_node_vars: Dict = {}
        if ansible_vars is None:
            ansible_vars = []
        fabric: str = self.get_current_fabric()
        # Get processors to be workload's ssh proxy
        if obj_type == ObjectKind.WORKLOAD.value:
            for obj_name in obj_list:
                ansible_node_vars[obj_name] = []
                obj_vpc: Dict = self.state['fabric'][fabric][obj_type][obj_name]['vpc']
                all_proc: List = [x for x in self.state['fabric'][fabric][ObjectKind.PROCESSOR.value].items()
                                  if x[1]['vpc'] == obj_vpc]
                success_proc: List = [x for x in self.state['fabric'][fabric][ObjectKind.PROCESSOR.value].items()
                                      if x[1]['vpc'] == obj_vpc and self.check_object_status(x[1],
                                                                                             ObjectStatus.SUCCESS)]
                if bool(all_proc):
                    # If there success created processors use it
                    if bool(success_proc):
                        ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                            'ip': success_proc[0][1]['properties']['ip']}))
                    else:  # Use any otherwise
                        ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                            'ip': all_proc[0][1]['properties']['ip']}))
                else:
                    log_error(
                        "Cannot provision {} {!r}. At least one processor should be present in VPC {!r}".format(
                            obj_type, obj_name, obj_vpc))
                    return False, 1
        # Get swarm manager if orchestrator
        if obj_type == ObjectKind.ORCHESTRATOR.value:
            manager: List = [x for x in self.state['fabric'][fabric][obj_type].items() if 'manager' in x[1]['role']]
            if bool(manager):
                ansible_vars = ansible_vars + [('env_swarm_manager_host', manager[0][0])]
                if manager[0][0] not in ansible_nodes:
                    ansible_nodes = ansible_nodes + [manager[0][0]]
                    ansible_vars = ansible_vars + [('env_swarm_manager_only', True)]
            else:
                log_error('Cannot update {0}. There is swarm manager role missing'.format(obj_type))
                return False, 1
        # Run ansible playbook
        ansible = Ansible(self, fabric, self.get_ssh_key())
        if ansible.inventory_generate(ansible_nodes, node_vars=ansible_vars, per_node_vars=ansible_node_vars):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error(
                    'Cannot update {0}s: {1!r}. There is issue with ansible playbook execution'.format(obj_type,
                                                                                                       obj_list))
                for obj_name in obj_list:
                    obj: Dict = self.state['fabric'][fabric][obj_type][obj_name]
                    self.set_object_state_status(obj, ObjectState.UPDATED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            else:
                log_ok("{0}s {1!r} updated successfully".format(obj_type.title(), obj_list))
                for obj_name in obj_list:
                    obj = self.state['fabric'][fabric][obj_type][obj_name]
                    self.set_object_state_status(obj, ObjectState.UPDATED, ObjectStatus.SUCCESS)
                return True, 0
        else:
            return False, 1

    def workload_restart(self, fabric_name: str, workload_list: List) -> Tuple:
        """Start workloads"""
        # Start workload
        ansible_nodes: List = workload_list[:]
        ansible_node_vars: Dict = {}
        ansible_playbook: str = "restart-workload.yml"
        # Get processors to be workload's ssh proxy
        for obj_name in workload_list:
            ansible_node_vars[obj_name] = []
            obj_vpc: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][obj_name]['vpc']
            all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                              x[1]['vpc'] == obj_vpc]
            success_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                                  x[1]['vpc'] == obj_vpc and self.check_object_status(x[1], ObjectStatus.SUCCESS)]
            if bool(all_proc):
                # If there success created processors use it
                if bool(success_proc):
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                        'ip': success_proc[0][1]['properties']['ip']}))
                else:  # Use any otherwise
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                        'ip': all_proc[0][1]['properties']['ip']}))
            else:
                log_error("Cannot provision workload {!r}. At least one processor should be present in VPC \
                            {!r}".format(obj_name, obj_vpc))
                return False, 1
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes, per_node_vars=ansible_node_vars):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot restart workloads. There is issue with ansible playbook execution')
                for workload_name in workload_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                    self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for workload_name in workload_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.SUCCESS)
            log_ok("Workloads {0!r} restarted successfully".format(workload_list))
            return True, 0
        else:
            return False, 1

    def processor_restart(self, fabric_name: str, processor_list: List) -> Tuple:
        """Start processor_list"""
        # Start processor
        ansible_nodes: List = processor_list[:]
        ansible_playbook: str = "restart-processor.yml"
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot restart processors. There is issue with ansible playbook execution')
                for processor_name in processor_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                    self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for processor_name in processor_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.SUCCESS)
            log_ok("Processors {0!r} restarted successfully".format(processor_list))
            return True, 0
        else:
            return False, 1

    def workload_start(self, fabric_name: str, workload_list: List) -> Tuple:
        """Start workloads"""
        # Start workload
        ansible_nodes: List = workload_list[:]
        ansible_node_vars: Dict = {}
        ansible_playbook: str = "start-workload.yml"
        # Get processors to be workload's ssh proxy
        for obj_name in workload_list:
            ansible_node_vars[obj_name] = []
            obj_vpc: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][obj_name]['vpc']
            all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                              x[1]['vpc'] == obj_vpc]
            success_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                                  x[1]['vpc'] == obj_vpc and self.check_object_status(x[1], ObjectStatus.SUCCESS)]
            if bool(all_proc):
                # If there success created processors use it
                if bool(success_proc):
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                        'ip': success_proc[0][1]['properties']['ip']}))
                else:  # Use any otherwise
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                        'ip': all_proc[0][1]['properties']['ip']}))
            else:
                log_error("Cannot provision workload {!r}. At least one processor should be present in VPC \
                            {!r}".format(obj_name, obj_vpc))
                return False, 1
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes, per_node_vars=ansible_node_vars):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot start workloads. There is issue with ansible playbook execution')
                for workload_name in workload_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                    self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for workload_name in workload_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.SUCCESS)
            log_ok("Workloads {0!r} started successfully".format(workload_list))
            return True, 0
        else:
            return False, 1

    def processor_start(self, fabric_name: str, processor_list: List) -> Tuple:
        """Start processor_list"""
        # Start processor
        ansible_nodes: List = processor_list[:]
        ansible_playbook: str = "start-processor.yml"
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot start processors. There is issue with ansible playbook execution')
                for processor_name in processor_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                    self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for processor_name in processor_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                self.set_object_state_status(obj, ObjectState.STARTED, ObjectStatus.SUCCESS)
            log_ok("Processors {0!r} started successfully".format(processor_list))
            return True, 0
        else:
            return False, 1

    def workload_stop(self, fabric_name: str, workload_list: List) -> Tuple:
        """Stop workloads"""
        # Start workload
        ansible_nodes: List = workload_list[:]
        ansible_node_vars: Dict = {}
        ansible_playbook: str = "stop-workload.yml"
        # Get processors to be workload's ssh proxy
        for obj_name in workload_list:
            ansible_node_vars[obj_name] = []
            obj_vpc: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][obj_name]['vpc']
            all_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                              x[1]['vpc'] == obj_vpc]
            success_proc: List = [x for x in self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value].items() if
                                  x[1]['vpc'] == obj_vpc and self.check_object_status(x[1], ObjectStatus.SUCCESS)]
            if bool(all_proc):
                # If there success created processors use it
                if bool(success_proc):
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': success_proc[0][0],
                                                        'ip': success_proc[0][1]['properties']['ip']}))
                else:  # Use any otherwise
                    ansible_node_vars[obj_name].append(('ssh_proxy_host', {'name': all_proc[0][0],
                                                        'ip': all_proc[0][1]['properties']['ip']}))
            else:
                log_error("Cannot provision workload {!r}. At least one processor should be present in VPC \
                            {!r}".format(obj_name, obj_vpc))
                return False, 1
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes, per_node_vars=ansible_node_vars):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot stop workloads. There is issue with ansible playbook execution')
                for workload_name in workload_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                    self.set_object_state_status(obj, ObjectState.STOPPED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for workload_name in workload_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.WORKLOAD.value][workload_name]
                self.set_object_state_status(obj, ObjectState.STOPPED, ObjectStatus.SUCCESS)
            log_ok("Workloads {0!r} stopped successfully".format(workload_list))
            return True, 0
        else:
            return False, 1

    def processor_stop(self, fabric_name: str, processor_list: List) -> Tuple:
        """Stop processors"""
        # Start processor
        ansible_nodes: List = processor_list[:]
        ansible_playbook: str = "stop-processor.yml"
        # Run ansible playbook
        ansible = Ansible(self, fabric_name, self.get_ssh_key(fabric_name))
        if ansible.inventory_generate(ansible_nodes):
            ansible_result: Tuple = ansible.run_playbook(ansible_playbook)
            if not ansible_result[0]:
                log_error('Cannot stop processors. There is issue with ansible playbook execution')
                for processor_name in processor_list:
                    obj: Dict = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                    self.set_object_state_status(obj, ObjectState.STOPPED, ObjectStatus.FAILED)
                return False, ansible_result[1]
            for processor_name in processor_list:
                obj = self.state['fabric'][fabric_name][ObjectKind.PROCESSOR.value][processor_name]
                self.set_object_state_status(obj, ObjectState.STOPPED, ObjectStatus.SUCCESS)
            log_ok("Processors {0!r} stopped successfully".format(processor_list))
            return True, 0
        else:
            return False, 1

    def vpc_create(self, fabric_name: str, vpc_list: List) -> Tuple:
        """Creates vpc from state (terraform)"""
        # Get credentials
        credentials = Credentials(fabric_name, self.state, self.config)
        if not credentials.get():
            log_error('Cannot create VPC. Not able to get credentials')
            return False, 1
        # Run Terraform with new state
        terraform = Terraform(fabric_name, self, credentials, self.version)
        if not terraform.plan_generate():
            log_error('Cannot create VPC. There is issue with terraform plan generation')
            for vpc in vpc_list:
                self.set_object_state_status(self.state['fabric'][fabric_name]['vpc'][vpc], ObjectState.CREATED,
                                             ObjectStatus.FAILED)
            return False, 1
        terraform_result: Tuple = terraform.plan_execute()
        if not terraform_result[0]:
            log_error('Cannot create VPC. There is issue with terraform plan execution')
            for vpc in vpc_list:
                self.set_object_state_status(self.state['fabric'][fabric_name]['vpc'][vpc], ObjectState.CREATED,
                                             ObjectStatus.FAILED)
            return False, terraform_result[1]
        # Set new state to be current and dump it
        for vpc in vpc_list:
            self.set_object_state_status(self.state['fabric'][fabric_name]['vpc'][vpc], ObjectState.CREATED,
                                         ObjectStatus.SUCCESS)
        log_ok("VPCs {0!r} created successfully".format(vpc_list))
        return True, 0

    def nodebatch_check_success(self, nodebatch_targets: List, target_obj_state: ObjectState,
                                nodebatch_type: ObjectKind) -> bool:
        """Checks if batches are finished"""
        nodebatch_list: List = nodebatch_targets[:]
        for nodebatch in nodebatch_list:
            nodebatch_obj: Dict = self.get_nodebatch(nodebatch)
            nodebatch_curr_type: ObjectKind = ObjectKind.WORKLOAD
            if ObjectKind.PROCESSOR.value in nodebatch_obj:
                nodebatch_curr_type = ObjectKind.PROCESSOR
            if self.check_object_state(nodebatch_obj, target_obj_state) and \
                    nodebatch_curr_type == nodebatch_type:
                log_info('Node batch {0!r} is successful, removing from state'.format(nodebatch))
                res: Result = self.delete_nodebatch(nodebatch)
                if not res.status:
                    return False
                nodebatch_targets.remove(nodebatch)
        return True

    def nodebatch_delete(self, fabric: Any = None, vpc: Any = None) -> bool:
        """Deletes node batches for fabric or vpc"""
        nodebatches: List = []
        workloads: List = []
        processors: List = []
        entity: str = ""
        entity_type: str = ""
        for batch in self.state['batch']:
            if vpc is not None:
                if ObjectKind.WORKLOAD.value in self.state['batch'][batch]:
                    workloads = [item[1] for item in self.state['batch'][batch][ObjectKind.WORKLOAD.value].items() if
                                 item[1]['spec']['vpc'] == vpc]
                if ObjectKind.PROCESSOR.value in self.state['batch'][batch]:
                    processors = [item[1] for item in self.state['batch'][batch][ObjectKind.PROCESSOR.value].items() if
                                  item[1]['spec']['vpc'] == vpc]
                nodes: List = workloads + processors
                entity_type = 'VPC'
                entity = vpc
            elif fabric is not None:
                if ObjectKind.WORKLOAD.value in self.state['batch'][batch]:
                    workloads = [item[1] for item in self.state['batch'][batch][ObjectKind.WORKLOAD.value].items() if
                                 item[1]['metadata']['fabric'] == fabric]
                if ObjectKind.PROCESSOR.value in self.state['batch'][batch]:
                    processors = [item[1] for item in self.state['batch'][batch][ObjectKind.PROCESSOR.value].items() if
                                  item[1]['metadata']['fabric'] == fabric]
                nodes = workloads + processors
                entity_type = 'fabric'
                entity = fabric
            else:
                return False
            if bool(nodes):
                nodebatches.append(batch)
        if bool(nodebatches):
            log_warn("Active node batches found: {!r} in {} {!r}, going to be deleted"
                     .format(nodebatches, entity_type, entity))
            for batch in nodebatches:
                self.delete_nodebatch(batch)
        return True

    def configure_actions_list(self, entity_type: str, entity_list: List) -> Dict:
        """Returns actions sequence to configure from every state"""
        actions: Dict = {'config': [], 'start': [], 'stop': [], 'update': []}
        for entity in entity_list:
            current_state: ObjectState = \
                self.get_object_state(
                    self.state[ObjectKind.FABRIC.value][self.get_current_fabric()][entity_type][entity]
                )
            if current_state == ObjectState.CREATED:
                actions['config'].append(entity)
            elif current_state == ObjectState.CONFIGURED:
                actions['config'].append(entity)
            elif current_state == ObjectState.STARTED:
                actions['config'].append(entity)
                actions['start'].append(entity)
            elif current_state == ObjectState.STOPPED:
                actions['config'].append(entity)
                actions['stop'].append(entity)
        return actions

    def update_actions_list(self, entity_type: str, entity_list: List) -> Dict:
        """Returns actions sequence to update from every state"""
        actions: Dict = {'config': [], 'start': [], 'stop': [], 'update': []}
        for entity in entity_list:
            current_state: ObjectState = \
                self.get_object_state(
                    self.state[ObjectKind.FABRIC.value][self.get_current_fabric()][entity_type][entity]
                )
            if current_state in [ObjectState.CREATED, ObjectState.UPDATED]:
                actions['update'].append(entity)
            if current_state == ObjectState.CONFIGURED:
                actions['update'].append(entity)
                actions['config'].append(entity)
            elif current_state == ObjectState.STARTED:
                actions['update'].append(entity)
                actions['start'].append(entity)
            elif current_state == ObjectState.STOPPED:
                actions['update'].append(entity)
                actions['stop'].append(entity)
        return actions

    def credentials_set(self, fabric: str, path: str) -> bool:
        """Set credentials to state"""
        if 'credentialsFile' not in self.state['fabric'][fabric]['config']:
            self.state['fabric'][fabric]['config']['credentialsFile'] = {}
        self.state['fabric'][fabric]['config']['credentialsFile'] = path
        return True

    def get_processor_spec_from_batch(self, entity: List) -> Dict:
        """Returns processor config from batch"""
        new_processor: Dict = self.get_clean_processor()
        for config_param in entity[0]['spec']['config']:
            new_processor['config'][config_param] = entity[0]['spec']['config'][config_param]
        return new_processor['config']

    def get_workload_spec_from_batch(self, entity: List) -> Dict:
        """Returns workload config from batch"""
        new_workload: Dict = self.get_clean_workload()
        for config_param in entity[0]['spec']['config']:
            new_workload['config'][config_param] = entity[0]['spec']['config'][config_param]
        return new_workload['config']
