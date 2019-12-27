import os
import re
import sys
from copy import deepcopy

import click
from bwctl.session.credentials import Credentials
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_ok, log_warn, log_info
from bwctl.utils.states import ObjectKind, ObjectStatus, ObjectState


@click.group('configure', cls=AliasedGroup)
def configure_cmd():
    """Configure commands"""
    pass


@configure_cmd.command('workload')
@click.pass_context
@click.argument('workload-name', default=False)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
@click.option('--orchestrator-fqdn', required=False)
@click.option('--location', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--file', required=False, default=None)
def config_workload(ctx, workload_name, all_nodes, orchestrator_fqdn, location, dry_run, file):
    """Configure workload"""
    obj_kind = ObjectKind.WORKLOAD.value
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot configure {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Check target objects to be used
    obj_list = []
    if all_nodes:
        if workload_name:
            log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                       if temp_state.check_object_state(x[1], ObjectState.CREATED) and
                       temp_state.check_object_status(x[1], ObjectStatus.SUCCESS)]
        obj_created_failed = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                              if temp_state.check_object_state(x[1], ObjectState.CREATED) and
                              temp_state.check_object_status(x[1], ObjectStatus.FAILED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                        if temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created_failed]
        if not obj_list:
            states = [ObjectState.CREATED.value, ObjectState.CONFIGURED.value, ObjectState.UPDATED.value,
                      ObjectState.STARTED.value, ObjectState.STOPPED.value]
            log_error("Cannot configure. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created and orchestrator_fqdn is None:
            log_error('Cannot configure {}. Option "--orchestrator-fqdn" is required by {!r}'.format(
                obj_kind.lower(), obj_created))
            sys.exit(1)
        if obj_created_failed:
            log_warn('There are failed {}s during creation: {!r}. Skipping...'.format(obj_kind.lower(),
                                                                                      obj_created_failed))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
    elif workload_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, workload_name)
        # Check if exist
        if not temp_state.check_workload(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot configure. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, workload_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED):
            if orchestrator_fqdn is None:
                log_error('Cannot configure. Missing option "--orchestrator-fqdn"')
                sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED) and \
                temp_state.check_object_status(obj, ObjectStatus.FAILED):
            log_error("{0} was created with failures. Run create {1} again before configure".format(obj_kind.title(),
                                                                                                    obj_kind))
            sys.exit(1)
        obj_list = [workload_name]
    elif workload_name is None:
        log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Set configuration
    for obj_name in obj_list:
        obj = temp_state.get_fabric_object(obj_kind, obj_name)
        if orchestrator_fqdn is not None:
            obj['config']['orchestrator'] = orchestrator_fqdn
        if location is not None:
            obj['config']['location'] = location
    if orchestrator_fqdn is None:
        log_warn('{0}s {1!r} to be re-configured'.format(obj_kind.title(), obj_list))
    # Configure dry-run
    if dry_run:
        log_warn('{0}s {1!r} to be configured (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    actions_list = temp_state.configure_actions_list(obj_kind, obj_list)
    if actions_list['config']:
        res = temp_state.workload_configure(temp_state.get_current_fabric(), actions_list['config'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    if actions_list['stop']:
        res = ctx.obj.state.workload_stop(temp_state.get_current_fabric(), actions_list['stop'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    if actions_list['start']:
        res = ctx.obj.state.workload_start(temp_state.get_current_fabric(), actions_list['start'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if file:
        click.echo('File: {0}'.format(file))
    return True


@configure_cmd.command('orchestrator')
@click.pass_context
@click.argument('orchestrator-name', required=False)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--file', required=False, default=None)
def config_orchestrator(ctx, orchestrator_name, all_nodes, dry_run, file):
    """Configure orchestrator"""
    obj_kind = ObjectKind.ORCHESTRATOR.value
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot configure {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Check target objects to be used
    obj_list = []
    if all_nodes:
        if orchestrator_name:
            log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created_failed = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                              if temp_state.check_object_state(x[1], ObjectState.CREATED) and
                              temp_state.check_object_status(x[1], ObjectStatus.FAILED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                        if temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created_failed]
        if not obj_list:
            states = [ObjectState.CREATED.value, ObjectState.CONFIGURED.value, ObjectState.UPDATED.value]
            log_error("Cannot configure. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created_failed:
            log_warn('There are failed {}s during creation: {!r}. Skipping...'.format(obj_kind.lower(),
                                                                                      obj_created_failed))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
    elif orchestrator_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, orchestrator_name)
        # Check if exist
        if not temp_state.check_orchestrator(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot configure. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, orchestrator_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED) and \
                temp_state.check_object_status(obj, ObjectStatus.FAILED):
            log_error("{0} was created with failures. Run create {1} again before configure".format(obj_kind.title(),
                                                                                                    obj_kind))
            sys.exit(1)
        obj_list = [orchestrator_name]
    elif orchestrator_name is None:
        log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Configure dry-run
    if dry_run:
        log_warn('{0}s {1!r} to be configured (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    # Check if controller and telemetry are not configured yet
    passwd_controller = None
    passwd_grafana = None
    for orch in obj_list:
        obj = temp_state.get_fabric_object(obj_kind, orch)
        if obj['type'] == 'controller' and temp_state.check_object_state(obj, ObjectState.CREATED) and \
                temp_state.check_object_status(obj, ObjectStatus.SUCCESS):
            passwd_controller = temp_state.get_passwd()
        if obj['type'] == 'telemetry' and temp_state.check_object_state(obj, ObjectState.CREATED) and \
                temp_state.check_object_status(obj, ObjectStatus.SUCCESS):
            passwd_grafana = temp_state.get_passwd()
    # Check dockerhub credentials
    credentials = None
    for orch in obj_list:
        obj = temp_state.get_fabric_object(obj_kind, orch)
        if obj['type'] == 'controller':
            credentials = Credentials(temp_state.get_current_fabric(), temp_state.get(), ctx.obj.state.config)
            if not credentials.get_docker():
                log_error('Cannot configure. Not able to get Bayware dockerhub credentials')
                sys.exit(1)
    # Configure orchestrator
    res = temp_state.orchestrator_configure(temp_state.get_current_fabric(), obj_list,
                                            controller_passwd=passwd_controller, grafana_passwd=passwd_grafana,
                                            credentials=credentials)
    if not res[0]:
        sys.exit(res[1])
    # Show grafana password
    if passwd_grafana is not None:
        temp_state.show_passwd(passwd_grafana, 'grafana')
    # Show controller password
    if passwd_controller is not None:
        temp_state.show_passwd(passwd_controller, 'controller')
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if file:
        click.echo('File: {0}'.format(file))
    return True


@configure_cmd.command('processor')
@click.pass_context
@click.argument('processor-name', required=False)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
@click.option('--orchestrator-fqdn', required=False)
@click.option('--location', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--file', required=False, default=None)
def config_processor(ctx, processor_name, all_nodes, orchestrator_fqdn, location, dry_run, file):
    """Configure processor"""
    obj_kind = ObjectKind.PROCESSOR.value
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot configure {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Check target objects to be used
    obj_list = []
    if all_nodes:
        if processor_name:
            log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                       if temp_state.check_object_state(x[1], ObjectState.CREATED) and
                       temp_state.check_object_status(x[1], ObjectStatus.SUCCESS)]
        obj_created_failed = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                              if temp_state.check_object_state(x[1], ObjectState.CREATED) and
                              temp_state.check_object_status(x[1], ObjectStatus.FAILED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()
                        if temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created_failed]
        if not obj_list:
            states = [ObjectState.CREATED.value, ObjectState.CONFIGURED.value, ObjectState.UPDATED.value,
                      ObjectState.STARTED.value, ObjectState.STOPPED.value]
            log_error("Cannot configure. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created and orchestrator_fqdn is None:
            log_error('Cannot configure {}. Option "--orchestrator-fqdn" is required by {!r}'.format(
                obj_kind.lower(), obj_created))
            sys.exit(1)
        if obj_created_failed:
            log_warn('There are failed {}s during creation: {!r}. Skipping...'.format(obj_kind.lower(),
                                                                                      obj_created_failed))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
    elif processor_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, processor_name)
        # Check if exist
        if not temp_state.check_processor(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot configure. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, processor_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED):
            if orchestrator_fqdn is None:
                log_error('Cannot configure. Missing option "--orchestrator-fqdn"')
                sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED) and \
                temp_state.check_object_status(obj, ObjectStatus.FAILED):
            log_error("{0} was created with failures. Run create {1} again before configure".format(obj_kind.title(),
                                                                                                    obj_kind))
            sys.exit(1)
        obj_list = [processor_name]
    elif processor_name is None:
        log_error("Cannot configure. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Set configuration
    for obj_name in obj_list:
        obj = temp_state.get_fabric_object(obj_kind, obj_name)
        if orchestrator_fqdn is not None:
            obj['config']['orchestrator'] = orchestrator_fqdn
        if location is not None:
            obj['config']['location'] = location
    if orchestrator_fqdn is None:
        log_warn('{0}s {1!r} to be re-configured'.format(obj_kind.title(), obj_list))
    # Configure dry-run
    if dry_run:
        log_warn('{0}s {1!r} to be configured (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    actions_list = temp_state.configure_actions_list(obj_kind, obj_list)
    if actions_list['config']:
        res = temp_state.processor_configure(temp_state.get_current_fabric(), actions_list['config'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    if actions_list['stop']:
        res = temp_state.processor_stop(temp_state.get_current_fabric(), actions_list['stop'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    if actions_list['start']:
        res = temp_state.processor_start(temp_state.get_current_fabric(), actions_list['start'])
        if not res[0]:
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
            sys.exit(res[1])
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if file:
        click.echo('File: {0}'.format(file))
    return True


@configure_cmd.command('fabric')
@click.pass_context
@click.argument('fabric-name')
@click.option('--credentials-file', required=False, default=None)
@click.option('--ssh-private-key', required=False, default=None)
def config_fabric(ctx, fabric_name, credentials_file, ssh_private_key):
    """Configure fabric"""
    # Check if naming matches rules
    fabric_name = ctx.obj.state.normalise_state_obj_name('fabric', fabric_name)
    company_name = ctx.obj.state.normalise_state_obj_name(
        'company-name', ctx.obj.state.config.get_attr('fabric_manager')['company_name'])
    if bool(company_name):
        pattern_string = "^[a-zA-Z0-9-]+$"
        pattern = re.compile(pattern_string)
        if not pattern.match(company_name):
            log_error("Cannot configure. Company name {0!r} doesn't match pattern {1!r}"
                      .format(company_name, pattern_string))
            sys.exit(1)
    else:
        log_error("Cannot configure fabric. Company name is required. Please run 'bwctl init' command or set "
                  "'fabric_manager.company_name' in {!r}".format(os.path.join(ctx.obj.state.config.dir,
                                                                              ctx.obj.state.config.file)))
        sys.exit(1)
    # Check if exist
    if not ctx.obj.state.check_fabric(fabric_name):
        log_error("Cannot configure. Fabric {0!r} doesn't exist".format(fabric_name))
        sys.exit(1)
    temp_state = deepcopy(ctx.obj.state)
    skip_ssh_keygen = False
    fabric = temp_state.get_fabric(fabric_name)
    # Set credentials
    cred_changed = False
    ssh_key_changed = False
    # Update credentials file if changed
    if bool(fabric['config']['credentialsFile']) and credentials_file is not None:
        if fabric['config']['credentialsFile'] != credentials_file:
            temp_state.credentials_set(fabric_name, credentials_file)
            log_info("Credentials file is set to {!r}".format(credentials_file))
            cred_changed = True
    # Check if ssh key file should be taken from config
    ssh_keys_cfg = ctx.obj.state.config.get_attr('ssh_keys')
    if bool(ssh_keys_cfg['private_key']) and ssh_private_key is None:
        ssh_private_key = ssh_keys_cfg['private_key']
    # Check if ssh key file is provided
    if ssh_private_key is not None:
        skip_ssh_keygen = True
        ssh_key_changed = True
        if 'privateKey' in fabric['config']['sshKeys']:
            if fabric['config']['sshKeys']['privateKey'] == ssh_private_key:
                ssh_key_changed = False
        temp_state.set_ssh_key(ssh_private_key, fabric_name)
        log_info("SSH private key is set to {!r}".format(ssh_private_key))
        credentials = Credentials(fabric_name, temp_state.get(), ctx.obj.state.config)
        if not credentials.check_ssh(ssh_private_key):
            log_error("Cannot configure fabric {0!r}. SSH keys issue".format(fabric_name))
            sys.exit(1)
    # Check fabric state and status
    if temp_state.check_object_state(fabric, ObjectState.DELETING) and not cred_changed:
        log_error("Cannot proceed, object is set for deletion!")
        sys.exit(1)
    elif temp_state.check_object_state(fabric, ObjectState.CONFIGURED) and \
            temp_state.check_object_status(fabric, ObjectStatus.SUCCESS):
        if ssh_key_changed:
            log_error("There is no possibility to change SSH key. Fabric {0!r} is already configured"
                      .format(fabric_name))
            sys.exit(1)
        if not cred_changed:
            log_error("Cannot configure. Fabric {0!r} is already configured".format(fabric_name))
            sys.exit(1)
    else:
        if temp_state.check_object_state(fabric, ObjectState.CREATED):
            # Set company name
            fabric['config']['companyName'] = company_name
        # Configure fabric
        res = temp_state.fabric_configure(fabric_name, skip_ssh_keygen)
        if not res[0]:
            sys.exit(res[1])
    if not temp_state.check_object_status(fabric, ObjectStatus.FAILED):
        log_ok("Fabric {0!r} configured successfully".format(fabric_name))

    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()


if __name__ == "__main__":
    configure_cmd()
