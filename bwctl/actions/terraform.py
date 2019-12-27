import os
import sys

import click
import sh
from bwctl.utils.common import check_process_running, log_info, log_error, log_warn
from bwctl.utils.templates import generate_from_template


class Terraform:
    """Manipulate terraform from templates"""

    def __init__(self, fabric=None, state=None, credentials=None, bwctl_version=None):
        """Initialise all attributes"""
        self.TERRAFORM_TEMPLATES = [
            'main.tf',
            'terraform.tfvars',
            'variables-aws.tf',
            'variables-azr.tf',
            'variables-gcp.tf',
            'variables-global.tf',
            'vpc-networking-aws.tf',
            'vpc-networking-azr.tf',
            'vpc-networking-gcp.tf',
            'vpc-orchestrator-aws.tf',
            'vpc-orchestrator-azr.tf',
            'vpc-orchestrator-gcp.tf',
            'vpc-processor-aws.tf',
            'vpc-processor-azr.tf',
            'vpc-processor-gcp.tf',
            'vpc-security-aws.tf',
            'vpc-security-azr.tf',
            'vpc-security-gcp.tf',
            'vpc-variables-aws.tf',
            'vpc-variables-azr.tf',
            'vpc-variables-gcp.tf',
            'vpc-workload-aws.tf',
            'vpc-workload-azr.tf',
            'vpc-workload-gcp.tf'
        ]
        self.bwctl_version = bwctl_version
        self.state = state.get()
        self.fabric = fabric
        self.config = state.config
        self.pub_key = state.get_ssh_pub_key(fabric)
        self.username = state.config.get_attr('username')
        # Get attributes from config
        components = self.config.get_attr('components')
        if components['branch'] == 'master':
            self.image_tag = 'stable'
        else:
            self.image_tag = 'unstable'
        self.image_family = str(components['family'])
        self.terraform_dir = os.path.join(self.config.dir, 'terraform', fabric)
        if self.config.get_attr('production'):
            self.production = "true"
        else:
            self.production = "false"
        self.hosted_zone = self.config.get_attr('hosted_zone')

        # Ensure terraform output directory exists
        try:
            os.makedirs(self.terraform_dir)
        except FileExistsError:
            # directory already exists
            pass

        # Initialise cloud provider credentials
        get_param = credentials.get_aws_param('aws_ec2_role')
        self.aws_ec2_role = get_param.value if get_param.status else False
        get_param = credentials.get_aws_param('aws_secret_access_key')
        self.aws_secret_key = get_param.value if get_param.status else ""
        get_param = credentials.get_aws_param('aws_access_key_id')
        self.aws_access_key_id = get_param.value if get_param.status else ""
        get_param = credentials.get_gcp_param('google_cloud_keyfile_json')
        self.gcp_credentials = get_param.value if get_param.status else ""
        get_param = credentials.get_gcp_param('project_id')
        self.gcp_project_name = get_param.value if get_param.status else ""
        get_param = credentials.get_azr_param('azr_client_id')
        self.azr_client_id = get_param.value if get_param.status else ""
        get_param = credentials.get_azr_param('azr_client_secret')
        self.azr_client_secret = get_param.value if get_param.status else ""
        get_param = credentials.get_azr_param('azr_resource_group_name')
        self.azr_resource_group_name = get_param.value if get_param.status else ""
        get_param = credentials.get_azr_param('azr_subscription_id')
        self.azr_subscription_id = get_param.value if get_param.status else ""
        get_param = credentials.get_azr_param('azr_tennant_id')
        self.azr_tennant_id = get_param.value if get_param.status else ""
        get_param = credentials.get_aws_param('aws_secret_access_key')
        self.s3_secret_key = get_param.value if get_param.status else ""
        get_param = credentials.get_aws_param('aws_access_key_id')
        self.s3_access_key_id = get_param.value if get_param.status else ""

    @staticmethod
    def terraform_process_output(line):
        """Print terraform output"""
        if bool(line.strip()):
            log_info(line.strip())

    def get_output_variable(self, module, variable):
        """Get output variable from terraform plan"""
        cwd = os.getcwd()
        os.chdir(self.terraform_dir)
        try:
            cmd = sh.terraform("output", "-module=" + module, variable)
        except sh.ErrorReturnCode as err:
            log_info(err.full_cmd)
            log_info('Command output:' + err.stdout.decode('UTF-8').rstrip())
            log_error(err.stderr.decode('UTF-8').rstrip(), nl=False)
            log_error("Unexpected terraform error during output (status code {0!r})".format(err.exit_code))
            os.chdir(cwd)
            return None
        os.chdir(cwd)
        if not bool(cmd.strip()):
            return None
        else:
            return cmd.strip()

    def get_output_variable_with_retries(self, module, variable, retries):
        """Get output variable from terraform plan (with retries)"""
        terraform_refresh = [
            "refresh", "-input=false",
            "-var", "gcp_credentials=" + self.gcp_credentials,
            "-var", "gcp_project_name=" + self.gcp_project_name,
            "-var", "azr_client_id=" + self.azr_client_id,
            "-var", "azr_client_secret=" + self.azr_client_secret,
            "-var", "azr_resource_group_name=" + self.azr_resource_group_name,
            "-var", "azr_subscription_id=" + self.azr_subscription_id,
            "-var", "azr_tennant_id=" + self.azr_tennant_id,
            "-var", "image_tag=" + self.image_tag,
            "-var", "image_version=" + self.image_family.replace(".", "-"),
            "-var", "dns_managed_zone_domain=" + self.hosted_zone,
            "-target=module." + module + ".azurerm_virtual_machine.vm"
        ]
        # Check if there AWS keys or EC2 role should be used
        if not self.aws_ec2_role:
            terraform_refresh.append("-var")
            terraform_refresh.append("aws_secret_key={}".format(self.s3_secret_key))
            terraform_refresh.append("-var")
            terraform_refresh.append("aws_access_key={}".format(self.s3_access_key_id))
        log_info("Getting {0!r} output for {1!r} from terraform state...".format(variable, module))
        var = self.get_output_variable(module, variable)
        i = 1
        cwd = os.getcwd()
        os.chdir(self.terraform_dir)
        while var is None and i <= retries:
            log_warn('Retry to get {0!r} output from terraforn state. ({1} of {2})'.format(variable, i, retries))
            log_info('Refresh terraform module...')
            try:
                if not self.config.get_debug():
                    sh.terraform(terraform_refresh)
                else:
                    cmd = sh.terraform(terraform_refresh, _out=self.terraform_process_output, _bg=True)
                    cmd.wait()
            except sh.ErrorReturnCode as err:
                log_info(err.full_cmd)
                log_info('Command output:' + err.stdout.decode('UTF-8').rstrip())
                log_error(err.stderr.decode('UTF-8').rstrip(), nl=False)
                log_error("Unexpected terraform error during refresh (status code {0!r})".format(err.exit_code))
            var = self.get_output_variable(module, variable)
            i = i + 1
        os.chdir(cwd)
        return var

    @staticmethod
    def plan_dump(attr, filename):
        """Dump terraform template to a file"""
        # noinspection PyBroadException
        try:
            with open(filename, 'w') as dump_f:
                dump_f.write(attr)
            dump_f.close()
        except IOError as dump_err:
            log_error("{0} - I/O error({1}): {2}".format(filename, dump_err.errno, dump_err.strerror))
            return False
        except Exception:  # handle other exceptions such as attribute errors
            log_error("{0} - Unexpected error: {1}".format(filename, sys.exc_info()[0]))
            return False
        return True

    def plan_generate(self):
        """Generate terraform plan"""
        log_info("Generate terraform plan...")

        def show_item(item):
            """Print current item"""
            if item is not None:
                return '-> {0!s}'.format(item)

        with click.progressbar(self.TERRAFORM_TEMPLATES, item_show_func=show_item) as bar:
            for template in bar:
                dst_filename = os.path.join(self.terraform_dir, template)
                if not self.plan_dump(
                        generate_from_template(self.state, self.fabric, self.hosted_zone, self.pub_key,
                                               self.config.get_attr('cloud_storage'),
                                               self.config.get_attr('fabric_manager'), self.username, self.aws_ec2_role,
                                               template + '.j2'),
                        dst_filename):
                    return False
        return True

    def plan_execute(self):
        """Execute terraform plan"""
        terraform_steps = {
            'init': [
                "init", "-input=false",
                "-force-copy"
            ],
            'apply': [
                "apply", "-input=false",
                "-var", "gcp_credentials=" + self.gcp_credentials,
                "-var", "gcp_project_name=" + self.gcp_project_name,
                "-var", "azr_client_id=" + self.azr_client_id,
                "-var", "azr_client_secret=" + self.azr_client_secret,
                "-var", "azr_resource_group_name=" + self.azr_resource_group_name,
                "-var", "azr_subscription_id=" + self.azr_subscription_id,
                "-var", "azr_tennant_id=" + self.azr_tennant_id,
                "-var", "production=" + self.production,
                "-var", "bastion_ip=" + self.config.get_attr('fabric_manager')['ip'],
                "-var", "image_tag=" + self.image_tag,
                "-var", "image_version=" + self.image_family.replace(".", "-"),
                "-var", "dns_managed_zone_domain=" + self.hosted_zone,
                "-auto-approve"
            ]
        }
        # Check if there AWS keys or EC2 role should be used
        if not self.aws_ec2_role:
            terraform_steps['init'].append("-backend-config=secret_key={}".format(self.s3_secret_key))
            terraform_steps['init'].append("-backend-config=access_key={}".format(self.s3_access_key_id))
            terraform_steps['apply'].append("-var")
            terraform_steps['apply'].append("aws_secret_key={}".format(self.s3_secret_key))
            terraform_steps['apply'].append("-var")
            terraform_steps['apply'].append("aws_access_key={}".format(self.s3_access_key_id))
        cwd = os.getcwd()
        log_info("Running terraform init and apply...")
        os.chdir(self.terraform_dir)
        # Check if there is any terraform already running
        proc_name = 'terraform'
        proc_result = check_process_running(proc_name)
        if proc_result[0]:
            log_error("There is already {!r} process (PID {!r}) running for user {!r}. Please retry again "
                      "later...".format(proc_name, str(proc_result[1]), proc_result[2]))
            return False, 1

        def show_step(item):
            """Print current step"""
            # We need to return next step as progressbar prints previously completed step
            if item is not None:
                t_keys = list(terraform_steps.keys())
                idx = t_keys.index(item)
                if idx == len(t_keys) - 1:
                    return '-> {0}'.format(item)
                else:
                    return '-> {0}'.format(t_keys[idx + 1])

        if not self.config.get_debug():
            with click.progressbar(terraform_steps, item_show_func=show_step, show_eta=False) as bar:
                for step in bar:
                    try:
                        sh.terraform(terraform_steps[step])
                    except sh.ErrorReturnCode as err:
                        log_info(err.full_cmd)
                        log_info('Command output:' + err.stdout.decode('UTF-8').rstrip())
                        log_error(err.stderr.decode('UTF-8').rstrip(), nl=False)
                        log_error("Unexpected terraform error during {0!s} (status code {1!r})".format(step,
                                                                                                       err.exit_code))
                        os.chdir(cwd)
                        return False, err.exit_code
        else:
            for step in terraform_steps:
                try:
                    cmd = sh.terraform(terraform_steps[step], _out=self.terraform_process_output, _bg=True)
                    cmd.wait()
                except sh.ErrorReturnCode as err:
                    log_info(err.full_cmd)
                    log_info('Command output:' + err.stdout.decode('UTF-8').rstrip())
                    log_error(err.stderr.decode('UTF-8').rstrip(), nl=False)
                    log_error("Unexpected terraform error during {0!s} (status code {1!r})".format(step,
                                                                                                   err.exit_code))
                    os.chdir(cwd)
                    return False, err.exit_code

        os.chdir(cwd)
        return True, 0


if __name__ == "__main__":
    Terraform()
