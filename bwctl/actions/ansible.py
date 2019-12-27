import json
import os
import re
import sys

import sh
from bwctl.utils.common import log_info, log_error
from bwctl.utils.states import ObjectKind


class Ansible:
    """Manipulate ansible provisioning"""

    def __init__(self, state=None, fabric=None, ansible_ssh_private_key_file=None):
        """Initialise all attributes"""

        # Initialise inventory
        self.inventory = {
            '_meta': {
                'hostvars': {}
            }
        }

        self.state = state.get()
        self.fabric = fabric
        self.debug = state.config.get_debug()
        self.hosted_zone = state.config.get_attr('hosted_zone')
        self.ansible_dir = state.ansible_dir
        self.ansible_user = state.config.get_attr('username')
        self.ansible_ssh_private_key_file = ansible_ssh_private_key_file
        self.ansible_ssh_controlpath_dir = "/tmp"
        self.config_dir = os.path.expanduser("~/.bwctl/")
        if bool(self.state['fabric'][fabric]['config']['companyName']):
            self.customer_company_name = self.state['fabric'][fabric]['config']['companyName']
        else:
            self.customer_company_name = ""

        # Ensure ansible output directory exists
        try:
            os.makedirs(self.ansible_dir)
        except FileExistsError:
            # directory already exists
            pass

    def add_inventory_group(self, groupname):
        """"Add host group to inventory"""
        if not bool(self.inventory.get(groupname)):
            self.inventory[groupname] = {
                'hosts': [],
                'children': [],
                'vars': {}
            }
        return True

    def add_inventory_host(self, hostname, ip_addr, fqdn, vpc_region, variables=None):
        """Add host"""
        if variables is None:
            variables = []
        self.inventory['_meta']['hostvars'][hostname] = {
            'ansible_host': ip_addr,
            'ansible_user': self.ansible_user,
            'ansible_ssh_private_key_file': self.ansible_ssh_private_key_file,
            'fqdn': fqdn,
            'vm_region': vpc_region,
            'env_fabric_name': self.fabric,
            'env_customer_company_name': self.customer_company_name,
            'env_hosted_zone': self.hosted_zone
        }
        for var in variables:
            self.inventory['_meta']['hostvars'][hostname][var[0]] = var[1]
            if var[0] == 'ssh_proxy_host':
                ansible_ssh_controlpath = os.path.join(self.ansible_ssh_controlpath_dir,
                                                       'bwctl-ansible-ssh-%r@%h:%p-{}'.format(var[1]['ip']))
                self.inventory['_meta']['hostvars'][hostname]['ansible_ssh_common_args'] = \
                    '-o ProxyCommand="ssh -W %h:%p -q {}@{} -i {}" -o ControlPath="{}"'.format(
                        self.ansible_user, var[1]['ip'], self.ansible_ssh_private_key_file, ansible_ssh_controlpath
                    )
        return True

    def add_group_host(self, hostname, groupname):
        """Append host to host group"""
        self.inventory[groupname].get('hosts', []).append(hostname)
        return True

    @staticmethod
    def inventory_dump(attr, filename):
        """Dump ansible inventory to a file"""
        # noinspection PyBroadException
        try:
            with open(filename, 'w') as dump_f:
                json.dump(attr, dump_f)
            dump_f.close()
        except IOError as dump_err:
            log_error("{0} - I/O error({1}): {2}".format(filename, dump_err.errno, dump_err.strerror))
            return False
        except Exception:  # handle other exceptions such as attribute errors
            log_error("{0} - Unexpected error: {1}".format(filename, sys.exc_info()[0]))
            return False
        return True

    def inventory_generate(self, node_list=None, node_vars=None, per_node_vars=None):
        """Generate ansible inventory"""
        state_fabric = self.state['fabric'][self.fabric]
        if node_vars is None:
            node_vars = []
        if node_list is None:
            node_list = []
            for obj_kind in [ObjectKind.ORCHESTRATOR.value, ObjectKind.PROCESSOR.value, ObjectKind.WORKLOAD.value]:
                node_list = node_list + list(state_fabric[obj_kind])
        if per_node_vars is None:
            per_node_vars = {}
        log_info("Generate ansible inventory...")
        self.add_inventory_group('all')
        for node in node_list:
            inventory_node_vars = node_vars[:]
            if node in per_node_vars:
                inventory_node_vars += per_node_vars[node]
            node_kind = ObjectKind.WORKLOAD.value
            node_fqdn = ''
            for kind in [ObjectKind.ORCHESTRATOR.value, ObjectKind.PROCESSOR.value, ObjectKind.WORKLOAD.value]:
                if node in state_fabric[kind]:
                    node_kind = kind
                    node_fqdn = state_fabric[node_kind][node]['properties']['fqdn']
            self.add_inventory_host(node, state_fabric[node_kind][node]['properties']['ip'], node_fqdn,
                                    state_fabric['vpc'][state_fabric[node_kind][node]['vpc']]['region'],
                                    inventory_node_vars)
            self.add_group_host(node, 'all')
            self.add_inventory_group(node_kind)
            self.add_group_host(node, node_kind)
            for node_cloud in ['aws', 'gcp', 'azr']:
                if node_cloud in state_fabric['vpc'][state_fabric[node_kind][node]['vpc']]['cloud']:
                    self.add_inventory_group(node_cloud)
                    self.add_group_host(node, node_cloud)
        for node in state_fabric['orchestrator']:
            for orch_type in ['controller', 'telemetry', 'events']:
                if orch_type in state_fabric['orchestrator'][node]['type']:
                    self.add_inventory_group(orch_type)
                    if node in node_list:
                        self.add_group_host(node, orch_type)
        dst_filename = os.path.join(self.config_dir, 'ansible_inventory')
        if not self.inventory_dump(self.inventory, dst_filename):
            return False
        return True

    def ansible_process_output(self, line):
        """Filter ansible output"""
        if not self.debug:
            if re.match("PLAY|TASK|RUNNING", line):
                log_info(line.strip().strip('* '))
        else:
            if bool(line.strip()):
                log_info(line.strip().strip('* '))

    def run_playbook(self, playbook_file_name, tag_list=None, local=None):
        """Run ansible playbook"""
        if not tag_list:
            tag_list = []
        log_info("Running ansible playbook {0!r}...".format(playbook_file_name))

        # Prepare env
        cwd = os.getcwd()
        os.chdir(self.ansible_dir)
        os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
        os.environ['ANSIBLE_RETRY_FILES_ENABLED'] = 'False'
        os.environ['ANSIBLE_SSH_RETRIES'] = '5'
        ansible_parameters = ["-i", "localhost,", "-c", "local", "-u", os.getenv('USER', ''),
                              "--extra-vars", "env_fabric_name=" + self.fabric,
                              "--extra-vars", "env_customer_company_name=" + self.customer_company_name,
                              "--extra-vars", "env_hosted_zone" + self.hosted_zone,
                              playbook_file_name]
        # Check if not local execution
        if local is None:
            ansible_parameters = ["-i", "ansible_inventory.sh", playbook_file_name]
        # Add tags if provided
        if tag_list:
            tags = ""
            ansible_parameters.append("--tags")
            for tag in tag_list:
                tags += tag + ","
            ansible_parameters.append(tags)
        # Run ansible playbook
        try:
            cmd = sh.ansible_playbook(ansible_parameters, _out=self.ansible_process_output, _bg=True)
            cmd.wait()
        except sh.ErrorReturnCode as err:
            log_info(err.full_cmd)
            log_info('Command output:' + err.stdout.decode('UTF-8').rstrip())
            log_error(err.stderr.decode('UTF-8').rstrip(), nl=False)
            log_error("Unexpected ansible playbook error (status code {0!r})".format(err.exit_code))
            if os.path.exists(cwd):
                os.chdir(cwd)
            return False, err.exit_code
        if os.path.exists(cwd):
            os.chdir(cwd)
        return True, 0


if __name__ == "__main__":
    Ansible()
