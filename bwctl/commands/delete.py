import sys
from copy import deepcopy

import click
import yaml
from bwctl.actions.ansible import Ansible
from bwctl.actions.batch_spec import BatchSpec
from bwctl.actions.ssh_config import SshConfig
from bwctl.actions.terraform import Terraform
from bwctl.session.credentials import Credentials
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_info, log_error, log_ok, log_warn
from bwctl.utils.states import ObjectStatus, ObjectState, ObjectKind


@click.group('delete', cls=AliasedGroup)
def delete_cmd():
    """Delete commands"""
    pass


@delete_cmd.command('batch')
@click.pass_context
@click.argument('filename')
@click.option('--input-format', required=False, type=click.Choice(['json', 'yaml']), default='yaml', show_default=True)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--yes', required=False, is_flag=True, default=False, show_default=True)
def delete_batch(ctx, filename, input_format, dry_run, yes):
    """Delete batch"""
    log_info('Deleting batch: file={!r}, input=format={!r}, dry-run={!r}'.format(filename, input_format, dry_run))
    # Only YAML currently
    if input_format != 'yaml':
        log_warn('Only YAML supported')

    # Safely load YAML
    # noinspection PyBroadException
    try:
        with open(filename, 'r') as config_f:
            try:
                batch = yaml.safe_load(config_f)
            except yaml.YAMLError as err:
                log_error("Error while loading YAML: {0!r}".format(err))
                if hasattr(err, 'problem_mark'):
                    mark = err.problem_mark
                    log_error("Error position: ({}:{})".format(mark.line + 1, mark.column + 1))
                sys.exit(1)
        config_f.close()
    except IOError as err:
        log_error(err)
        sys.exit(1)
    except Exception:  # handle other exceptions such as attribute errors
        print("Unexpected error:", sys.exc_info()[0])
        sys.exit(1)

    # Parse batch
    try:
        batch = BatchSpec(batch, ctx.obj.state.api_version)
    except TypeError as err:
        log_error("Cannot parse batch: {0!r}".format(err))
        sys.exit(1)

    # Get objects to be deleted (by fabric)
    delete_target = {}
    for obj_kind in [ObjectKind.FABRIC, ObjectKind.VPC, ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR,
                     ObjectKind.WORKLOAD]:
        for obj in batch.get_attr_list(obj_kind):
            if obj_kind == ObjectKind.FABRIC:
                fabric_name = obj['metadata']['name']
            else:
                fabric_name = obj['metadata']['fabric']
            if fabric_name not in delete_target:
                delete_target[fabric_name] = {ObjectKind.FABRIC: [], ObjectKind.VPC: [], ObjectKind.WORKLOAD: [],
                                              ObjectKind.ORCHESTRATOR: [], ObjectKind.PROCESSOR: []}
            delete_target[fabric_name][obj_kind].append(batch.get_attr_name(obj))

    for fabric in delete_target:
        for obj_kind in [ObjectKind.FABRIC, ObjectKind.VPC, ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR,
                         ObjectKind.WORKLOAD]:
            if obj_kind in delete_target[fabric]:
                if delete_target[fabric][obj_kind]:
                    log_info('{0}: {1!r}'.format(obj_kind.value.title(), delete_target[fabric][obj_kind]))

    def confirm_yes_no(message, default="no"):
        """Requires confirmation with yes/no"""
        valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
        prompt = " [y/N] "
        while True:
            log_info(message + prompt)
            choice = input().lower()
            if choice == '':
                return valid[default]
            elif choice in valid:
                return valid[choice]
            else:
                log_info("Please respond with 'yes' or 'no'")

    if not yes:
        if not confirm_yes_no('Do you want to delete these objects?'):
            log_info('Exiting...')
            return True

    # For all fabrics in delete target
    for fabric in delete_target:
        # Processing fabrics
        if fabric in delete_target[fabric][ObjectKind.FABRIC]:
            temp_state_ok = deepcopy(ctx.obj.state)
            temp_state_failed = deepcopy(ctx.obj.state)
            if temp_state_failed.check_fabric(fabric):
                log_warn('Fabric {0!r} is going to be deleted with all nested objects'.format(fabric))
                # Set deleting status in state
                temp_state_failed.set_object_state_status(temp_state_failed.get_fabric(fabric), ObjectState.DELETING,
                                                          ObjectStatus.FAILED)
                # Get nested objects
                nested = []
                for obj_kind in [ObjectKind.VPC, ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR, ObjectKind.WORKLOAD]:
                    nested.append([obj[0] for obj in
                                   temp_state_failed.get_fabric_objects(obj_kind.value, fabric).items()])
                # Set nested state to deleting
                for index, obj_kind in enumerate([ObjectKind.VPC, ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR,
                                                  ObjectKind.WORKLOAD]):
                    for obj_name in nested[index]:
                        obj = temp_state_failed.get_fabric_object(obj_kind.value, obj_name, fabric)
                        temp_state_failed.set_object_state_status(obj, ObjectState.DELETING, ObjectStatus.FAILED)
                        if obj_kind != ObjectKind.VPC:
                            res = temp_state_ok.delete_fabric_object(obj_kind.value, obj_name, fabric)
                            if not res.status:
                                log_error('Fabric {0!r} cannot be deleted. {1!s}'.format(fabric, res.value))
                                sys.exit(1)

                # Try to delete nodes-only nested objects
                nested_nodes = nested[1] + nested[2] + nested[3]
                if nested_nodes:
                    log_info("Deleting nested nodes first")
                    # Get credentials
                    credentials = Credentials(fabric, temp_state_failed.get(), ctx.obj.state.config)
                    if not credentials.get():
                        log_error('Batch failed. Not able to get credentials')
                        sys.exit(1)
                    # Run terraform
                    terraform = Terraform(fabric, temp_state_ok, credentials, ctx.obj.version)
                    if not terraform.plan_generate():
                        log_error('Batch failed to delete nested nodes: {!r}. Exiting'.format(nested_nodes))
                        ctx.obj.state = deepcopy(temp_state_failed)
                        ctx.obj.state.dump()
                        sys.exit(1)
                    terraform_result = terraform.plan_execute()
                    if not terraform_result[0]:
                        log_error('Batch failed to delete nested nodes: {!r}. Exiting'.format(nested_nodes))
                        ctx.obj.state = deepcopy(temp_state_failed)
                        ctx.obj.state.dump()
                        sys.exit(terraform_result[1])
                # If this is current fabric, unset it
                if temp_state_failed.get_current_fabric() == fabric:
                    ctx.obj.set_current_fabric(None)
                # Delete fabric from state
                res = temp_state_ok.delete_fabric(fabric)
                if not res.status:
                    log_error('Fabric {0!r} cannot be deleted. {1!s}'.format(fabric, res.value))
                    sys.exit(1)
                # Try to delete nested VPCs
                if nested[0]:
                    log_info("Deleting nested VPCs")
                    # Get credentials
                    credentials = Credentials(fabric, temp_state_failed.get(), ctx.obj.state.config)
                    if not credentials.get():
                        log_error('Batch failed. Not able to get credentials')
                        sys.exit(1)
                    # Run terraform
                    terraform = Terraform(fabric, temp_state_ok, credentials, ctx.obj.version)
                    if not terraform.plan_generate():
                        log_error('Batch failed to delete fabric: {!r}. Exiting'.format(fabric))
                        ctx.obj.state = deepcopy(temp_state_failed)
                        ctx.obj.state.dump()
                        sys.exit(1)
                    terraform_result = terraform.plan_execute()
                    if not terraform_result[0]:
                        log_error('Batch failed to delete fabric: {!r}. Exiting'.format(fabric))
                        ctx.obj.state = deepcopy(temp_state_failed)
                        ctx.obj.state.dump()
                        sys.exit(terraform_result[1])
                # Run ansible playbook
                ansible_playbook = "delete-fabric.yml"
                ansible = Ansible(temp_state_failed, fabric, temp_state_failed.get_ssh_key())
                log_info("Delete {0!r} fabric's files".format(fabric))
                ansible_result = ansible.run_playbook(ansible_playbook, local=True)
                if not ansible_result[0]:
                    log_error('Cannot delete fabric. There is issue with ansible playbook execution')
                    ctx.obj.state = deepcopy(temp_state_failed)
                    ctx.obj.dump()
                    sys.exit(ansible_result[1])
                # Delete fabrics batches
                temp_state_ok.nodebatch_delete(fabric=fabric)
                # Success
                ctx.obj.state = deepcopy(temp_state_ok)
                ctx.obj.state.dump()
        # Processing VPCs
        nested = {}
        temp_state_ok = deepcopy(ctx.obj.state)
        temp_state_failed = deepcopy(ctx.obj.state)
        # For all vpc in delete target
        vpc_list = delete_target[fabric][ObjectKind.VPC][:]
        for vpc in vpc_list:
            # Check if objects are exist
            if not temp_state_failed.check_fabric(fabric):
                delete_target[fabric][ObjectKind.VPC].remove(vpc)
                continue
            elif not temp_state_failed.check_vpc(fabric, vpc):
                delete_target[fabric][ObjectKind.VPC].remove(vpc)
                continue
            log_warn('VPC {0!r} is going to be deleted with all nested objects'.format(vpc))
            # Set deleting status in state
            obj = temp_state_failed.get_fabric_object(ObjectKind.VPC.value, vpc, fabric)
            temp_state_failed.set_object_state_status(obj, ObjectState.DELETING, ObjectStatus.FAILED)
            # Get nested objects
            nested[vpc] = []
            for obj_kind in [ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR, ObjectKind.WORKLOAD]:
                nested[vpc].append([obj[0] for obj in
                                    temp_state_failed.get_fabric_objects(obj_kind.value, fabric).items()
                                    if vpc in obj[1][ObjectKind.VPC.value]])
            # Set nested state to deleting
            for index, obj_kind in enumerate([ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR, ObjectKind.WORKLOAD]):
                for obj_name in nested[vpc][index]:
                    obj = temp_state_failed.get_fabric_object(obj_kind.value, obj_name, fabric)
                    temp_state_failed.set_object_state_status(obj, ObjectState.DELETING, ObjectStatus.FAILED)
                    res = temp_state_ok.delete_fabric_object(obj_kind.value, obj_name, fabric)
                    if not res.status:
                        log_error('Nested object {0!r} cannot be deleted. {1!s}'.format(obj_name, res.value))
                        sys.exit(1)
        # Try to delete nodes-only nested objects
        delete_nodes = False
        for vpc in delete_target[fabric][ObjectKind.VPC]:
            if nested[vpc][0] or nested[vpc][1] or nested[vpc][2]:
                delete_nodes = True
        if delete_nodes:
            log_info("Deleting nested nodes first")
            # Get credentials
            credentials = Credentials(fabric, temp_state_failed.get(), ctx.obj.state.config)
            if not credentials.get():
                log_error('Batch failed. Not able to get credentials')
                sys.exit(1)
            # Run terraform
            terraform = Terraform(fabric, temp_state_ok, credentials, ctx.obj.version)
            if not terraform.plan_generate():
                log_error('Batch failed to delete nodes, that nested to VPCs: {!r}. Exiting'.
                          format(delete_target[fabric][ObjectKind.VPC]))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(1)
            terraform_result = terraform.plan_execute()
            if not terraform_result[0]:
                log_error('Batch failed to delete nodes, that nested to VPCs: {!r}. Exiting'.
                          format(delete_target[fabric][ObjectKind.VPC]))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(terraform_result[1])
        # Delete VPC from state
        for vpc in delete_target[fabric][ObjectKind.VPC]:
            res = temp_state_ok.delete_fabric_object(ObjectKind.VPC.value, vpc, fabric)
            if not res.status:
                log_error('VPC {0!r} cannot be deleted. {1!s}'.format(vpc, res.value))
                sys.exit(1)
        # Actual VPC delete
        if delete_target[fabric][ObjectKind.VPC]:
            log_info("Deleting VPCs")
            # Get credentials
            credentials = Credentials(fabric, temp_state_failed.get(), ctx.obj.state.config)
            if not credentials.get():
                log_error('Batch failed. Not able to get credentials')
                sys.exit(1)
            # Run terraform
            terraform = Terraform(fabric, temp_state_ok, credentials, ctx.obj.version)
            if not terraform.plan_generate():
                log_error('Batch failed to delete VPCs: {!r}. Exiting'.format(delete_target[fabric][ObjectKind.VPC]))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(1)
            terraform_result = terraform.plan_execute()
            if not terraform_result[0]:
                log_error('Batch failed to delete VPCs: {!r}. Exiting'.format(delete_target[fabric][ObjectKind.VPC]))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(terraform_result[1])
        # Delete VPCs batches
        for vpc in delete_target[fabric][ObjectKind.VPC]:
            temp_state_ok.nodebatch_delete(vpc=vpc)
        # Success
        ctx.obj.state = deepcopy(temp_state_ok)
        ctx.obj.state.dump()
        # Processing nodes
        temp_state_ok = deepcopy(ctx.obj.state)
        temp_state_failed = deepcopy(ctx.obj.state)
        node_list = {}
        # For all nodes in delete target
        for obj_kind in [ObjectKind.ORCHESTRATOR, ObjectKind.PROCESSOR, ObjectKind.WORKLOAD]:
            node_list[obj_kind] = delete_target[fabric][obj_kind][:]
            for node in node_list[obj_kind]:
                # Check if objects are exist
                if not temp_state_failed.check_fabric(fabric):
                    delete_target[fabric][obj_kind].remove(node)
                    continue
                else:
                    if obj_kind is ObjectKind.ORCHESTRATOR:
                        if not temp_state_failed.check_orchestrator(fabric, node):
                            delete_target[fabric][obj_kind].remove(node)
                            continue
                    elif obj_kind is ObjectKind.PROCESSOR:
                        if not temp_state_failed.check_processor(fabric, node):
                            delete_target[fabric][obj_kind].remove(node)
                            continue
                    elif obj_kind is ObjectKind.WORKLOAD:
                        if not temp_state_failed.check_workload(fabric, node):
                            delete_target[fabric][obj_kind].remove(node)
                            continue
                # Set deleting status in state
                obj = temp_state_failed.get_fabric_object(obj_kind.value, node, fabric)
                temp_state_failed.set_object_state_status(obj, ObjectState.DELETING, ObjectStatus.FAILED)
                # Delete node from state
                res = temp_state_ok.delete_fabric_object(obj_kind.value, node, fabric)
                if not res.status:
                    log_error('Node {0!r} cannot be deleted. {1!s}'.format(node, res.value))
                    sys.exit(1)
        # Check if there is at least one processor left in VPC where workloads are present
        for proc in delete_target[fabric][ObjectKind.PROCESSOR][:]:
            # Check if its the only processor in VPC and there are workloads
            proc_vpc = temp_state_failed.get_fabric_object(ObjectKind.PROCESSOR.value, proc, fabric).get('vpc')
            processors = [x[0] for x in temp_state_ok.get_fabric_object(ObjectKind.PROCESSOR.value, fabric).items() if
                          proc_vpc == x[1]['vpc']]
            workloads = [x[0] for x in temp_state_ok.get_fabric_object(ObjectKind.WORKLOAD.value, fabric).items() if
                         proc_vpc == x[1]['vpc']]
            if not bool(processors) and bool(workloads):
                log_error("Cannot delete {0!r}. At least one {1} should left in VPC {2!r} to manage workloads: {3}"
                          .format(proc, ObjectKind.PROCESSOR.value.title(), proc_vpc, workloads))
                sys.exit(1)
        # Actual node delete
        if delete_target[fabric][ObjectKind.ORCHESTRATOR] or delete_target[fabric][ObjectKind.PROCESSOR] or \
                delete_target[fabric][ObjectKind.WORKLOAD]:
            # Get credentials
            credentials = Credentials(fabric, temp_state_failed.get(), ctx.obj.state.config)
            if not credentials.get():
                log_error('Batch failed. Not able to get credentials')
                sys.exit(1)
            # Run terraform
            terraform = Terraform(fabric, temp_state_ok, credentials, ctx.obj.version)
            if not terraform.plan_generate():
                delete_nodes = delete_target[fabric][ObjectKind.ORCHESTRATOR] + \
                               delete_target[fabric][ObjectKind.PROCESSOR] + delete_target[fabric][ObjectKind.WORKLOAD]
                log_error('Batch failed to delete nodes: {!r}. Exiting'.format(delete_nodes))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(1)
            terraform_result = terraform.plan_execute()
            if not terraform_result[0]:
                log_error('Batch failed to delete nodes: {!r}. Exiting'.format(delete_nodes))
                ctx.obj.state = deepcopy(temp_state_failed)
                ctx.obj.state.dump()
                sys.exit(terraform_result[1])
        # Success
        ctx.obj.state = deepcopy(temp_state_ok)
        ctx.obj.state.dump()
    log_ok('Batch is finished')
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@delete_cmd.command('fabric')
@click.pass_context
@click.argument('fabric-name')
def delete_fabric(ctx, fabric_name):
    """Delete fabric"""
    # Check if naming matches rules
    fabric_name = ctx.obj.state.normalise_state_obj_name('fabric', fabric_name)

    log_info('Deleting fabric {0!r}...'.format(fabric_name))
    # Check if fabric exists
    if not ctx.obj.state.check_fabric(fabric_name):
        log_error("Cannot delete. Fabric {0!r} doesn't exist".format(fabric_name))
        sys.exit(1)
    # Check for existing VPCs
    vpc_list = ctx.obj.state.get_fabric_objects('vpc', fabric_name).items()
    if vpc_list:
        log_error("Cannot delete. Fabric {0!r} contains VPCs, delete them first:".format(fabric_name))
        for vpc in vpc_list:
            log_error("{0!r}".format(vpc[0]))
        sys.exit(1)
    # Check for existing nodes
    node_list = []
    for obj_kind in [ObjectKind.ORCHESTRATOR.value, ObjectKind.PROCESSOR.value, ObjectKind.WORKLOAD.value]:
        node_list = node_list + list(ctx.obj.state.get_fabric_objects(obj_kind, fabric_name))
    if node_list:
        log_error("Cannot delete. Fabric {0!r} contains nodes, delete them first:".format(fabric_name))
        for node in node_list:
            log_error("{0!r}".format(node[0]))
        sys.exit(1)
    # Delete fabric
    ansible_playbook = "delete-fabric.yml"
    ansible = Ansible(ctx.obj.state, fabric_name, ctx.obj.state.get_ssh_key())
    log_info("Delete {0!r} fabric's files".format(fabric_name))
    ansible_result = ansible.run_playbook(ansible_playbook, local=True)
    if not ansible_result[0]:
        log_error('Cannot delete fabric. There is issue with ansible playbook execution')
        sys.exit(ansible_result[1])
    # If this is current fabric, unset it
    if ctx.obj.state.get_current_fabric() == fabric_name:
        ctx.obj.set_current_fabric(None)
    # Delete from state
    res = ctx.obj.state.delete_fabric(fabric_name)
    if not res.status:
        log_error('Fabric {0!r} cannot be deleted. {1!s}'.format(fabric_name, res.value))
        sys.exit(1)
    # Delete fabrics batches
    ctx.obj.state.nodebatch_delete(fabric=fabric_name)
    # Success
    log_ok('Fabric {0!r} deleted successfully'.format(fabric_name))
    ctx.obj.state.dump()
    return True


@delete_cmd.command('orchestrator')
@click.pass_context
@click.argument('orchestrator-name')
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def delete_orchestrator(ctx, orchestrator_name, dry_run):
    """Delete orchestrator"""
    obj_kind = ObjectKind.ORCHESTRATOR.value
    obj_name = orchestrator_name
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot delete {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, obj_name)

    log_info('Deleting {0} {1!r}...'.format(obj_kind, obj_name))
    # Check if exists
    if not ctx.obj.state.check_orchestrator(ctx.obj.state.get_current_fabric(), obj_name):
        log_error("Cannot delete. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
        sys.exit(1)

    if dry_run:
        log_warn('{0} {1!r} to be deleted (started with --dry-run)'.format(obj_kind.title(), obj_name))
        return True
    # Check if configured
    obj = ctx.obj.state.get_fabric_object(obj_kind, obj_name)
    if not ctx.obj.state.check_object_state(obj, ObjectState.CREATED):
        # Delete orchestrator
        ansible_vars = []
        ansible_nodes = [obj_name]
        ansible_playbook = "delete-" + obj['type'] + ".yml"
        # Get swarm manager
        managers = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if 'manager' in x[1]['role']]
        workers = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if 'worker' in x[1]['role']]
        if not managers:
            log_warn('There is no swarm manager found. Nothing should be done with ansible')
        else:
            # Check if manager and there are workers
            if obj['role'] == 'manager' and workers:
                log_error(
                    '{0} {1!r} is swarm manager. Remove workers first:'.format(obj_kind.title(), orchestrator_name))
                for node in workers:
                    log_error("{0!r}".format(node[0]))
                sys.exit(1)
            ansible_vars = ansible_vars + [('env_swarm_manager_host', managers[0][0])]
            ansible_nodes = ansible_nodes + [managers[0][0]]
            ansible = Ansible(ctx.obj.state, ctx.obj.state.get_current_fabric(), ctx.obj.state.get_ssh_key())
            if ansible.inventory_generate(ansible_nodes, node_vars=ansible_vars):
                ansible_result = ansible.run_playbook(ansible_playbook)
                if not ansible_result[0]:
                    log_error('Cannot delete {0}. There is issue with ansible playbook execution'.format(obj_kind))
                    sys.exit(ansible_result[1])
            else:
                sys.exit(1)
    # Get credentials
    credentials = Credentials(ctx.obj.state.get_current_fabric(), ctx.obj.state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot delete {0}. Not able to get credentials'.format(obj_kind))
        sys.exit(1)
    # Actual deletion
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.delete_fabric_object(obj_kind, obj_name)
    if not res.status:
        log_error('{0} {1!r} cannot be deleted. {2!s}'.format(obj_kind, obj_name, res.value))
        sys.exit(1)
    # Run Terraform with new state
    terraform = Terraform(temp_state.get_current_fabric(), temp_state, credentials, ctx.obj.version)
    if not terraform.plan_generate():
        log_error('Cannot delete {0}. There is issue with terraform plan generation'.format(obj_kind))
        sys.exit(1)
    terraform_result = terraform.plan_execute()
    if not terraform_result[0]:
        log_error('Cannot delete {0}. There is issue with terraform plan execution'.format(obj_kind))
        sys.exit(terraform_result[1])
    # Set new state to be current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    log_ok('{0} {1!r} deleted successfully'.format(obj_kind.title(), obj_name))
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@delete_cmd.command('processor')
@click.pass_context
@click.argument('processor-name')
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def delete_processor(ctx, processor_name, dry_run):
    """Delete processor"""
    obj_kind = ObjectKind.PROCESSOR.value
    obj_name = processor_name
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot delete {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, obj_name)

    log_info('Deleting {0} {1!r}...'.format(obj_kind, obj_name))
    # Check if exists
    if not ctx.obj.state.check_processor(ctx.obj.state.get_current_fabric(), obj_name):
        log_error("Cannot delete. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
        sys.exit(1)
    # Check if its the only processor in VPC and there are workloads
    obj_vpc = ctx.obj.state.get_fabric_object(obj_kind, obj_name)['vpc']
    processors = [x[0] for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if obj_vpc == x[1]['vpc']]
    workloads = [x[0] for x in ctx.obj.state.get_fabric_objects(ObjectKind.WORKLOAD.value).items()
                 if obj_vpc == x[1]['vpc']]
    if len(processors) < 2 and bool(workloads):
        log_error(
            "Cannot delete {0!r}. At least one {1} should left in VPC {2!r} to manage workloads: {3}".format(
                obj_name, obj_kind.title(), obj_vpc, workloads))
        sys.exit(1)

    if dry_run:
        log_warn('{0} {1!r} to be deleted (started with --dry-run)'.format(obj_kind.title(), obj_name))
        return True
    # Get credentials
    credentials = Credentials(ctx.obj.state.get_current_fabric(), ctx.obj.state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot delete {0}. Not able to get credentials'.format(obj_kind))
        sys.exit(1)
    # Actual deletion
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.delete_fabric_object(obj_kind, obj_name)
    if not res.status:
        log_error('{0} {1!r} cannot be deleted. {2!s}'.format(obj_kind, obj_name, res.value))
        sys.exit(1)
    # Run Terraform with new state
    terraform = Terraform(temp_state.get_current_fabric(), temp_state, credentials, ctx.obj.version)
    if not terraform.plan_generate():
        log_error('Cannot delete {0}. There is issue with terraform plan generation'.format(obj_kind))
        sys.exit(1)
    terraform_result = terraform.plan_execute()
    if not terraform_result[0]:
        log_error('Cannot delete {0}. There is issue with terraform plan execution'.format(obj_kind))
        sys.exit(terraform_result[1])
    # Set new state to be current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    log_ok('{0} {1!r} deleted successfully'.format(obj_kind.title(), obj_name))
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@delete_cmd.command('workload')
@click.pass_context
@click.argument('workload-name')
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def delete_workload(ctx, workload_name, dry_run):
    """Delete workload"""
    obj_kind = ObjectKind.WORKLOAD.value
    obj_name = workload_name
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot delete {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, obj_name)

    log_info('Deleting {0} {1!r}...'.format(obj_kind, obj_name))
    # Check if exists
    if not ctx.obj.state.check_workload(ctx.obj.state.get_current_fabric(), obj_name):
        log_error("Cannot delete. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
        sys.exit(1)

    if dry_run:
        log_warn('{0} {1!r} to be deleted (started with --dry-run)'.format(obj_kind.title(), obj_name))
        return True
    # Get credentials
    credentials = Credentials(ctx.obj.state.get_current_fabric(), ctx.obj.state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot delete {0}. Not able to get credentials'.format(obj_kind))
        sys.exit(1)
    # Actual deletion
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.delete_fabric_object(obj_kind, obj_name)
    if not res.status:
        log_error('{0} {1!r} cannot be deleted. {2!s}'.format(obj_kind, obj_name, res.value))
        sys.exit(1)
    # Run Terraform with new state
    terraform = Terraform(temp_state.get_current_fabric(), temp_state, credentials, ctx.obj.version)
    if not terraform.plan_generate():
        log_error('Cannot delete {0}. There is issue with terraform plan generation'.format(obj_kind))
        sys.exit(1)
    terraform_result = terraform.plan_execute()
    if not terraform_result[0]:
        log_error('Cannot delete {0}. There is issue with terraform plan execution'.format(obj_kind))
        sys.exit(terraform_result[1])
    # Set new state to be current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    log_ok('{0} {1!r} deleted successfully'.format(obj_kind.title(), obj_name))
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@delete_cmd.command('vpc')
@click.pass_context
@click.argument('vpc-name')
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def delete_vpc(ctx, vpc_name, dry_run):
    """Delete VPC"""
    obj_kind = ObjectKind.VPC.value
    obj_name = vpc_name
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot delete VPC. Please select fabric first.')
        sys.exit(1)
    # Check if naming matches rules
    obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, obj_name)

    log_info('Deleting VPC {0!r}...'.format(obj_name))
    # Check if VPC exists
    if not ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), obj_name):
        log_error("Cannot delete. VPC {0!r} doesn't exist".format(obj_name))
        sys.exit(1)
    # Check if there are nodes in VPC
    node_list = []
    for node_kind in [ObjectKind.ORCHESTRATOR.value, ObjectKind.PROCESSOR.value, ObjectKind.WORKLOAD.value]:
        node_list = node_list + [x for x in ctx.obj.state.get_fabric_objects(node_kind).items()
                                 if obj_name in x[1][obj_kind]]
    if node_list:
        log_error("Cannot delete. VPC {0!r} contains nodes, delete them first:".format(obj_name))
        for node in node_list:
            log_error("{0!r}".format(node[0]))
        sys.exit(1)
    # Delete VPC
    if dry_run:
        log_warn('{0} {1!r} to be deleted (started with --dry-run)'.format(obj_kind.upper(), obj_name))
        return True
    # Get credentials
    credentials = Credentials(ctx.obj.state.get_current_fabric(), ctx.obj.state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot delete VPC. Not able to get credentials')
        sys.exit(1)
    # Actual VPC deletion
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.delete_fabric_object(obj_kind, obj_name)
    if not res.status:
        log_error('{0} {1!r} cannot be deleted. {2!s}'.format(obj_kind.upper(), obj_name, res.value))
        sys.exit(1)
    # Run Terraform with new state
    terraform = Terraform(temp_state.get_current_fabric(), temp_state, credentials, ctx.obj.version)
    if not terraform.plan_generate():
        log_error('Cannot delete VPC. There is issue with terraform plan generation')
        sys.exit(1)

    terraform_result = terraform.plan_execute()
    if not terraform_result[0]:
        log_error('Cannot delete VPC. There is issue with terraform plan execution')
        sys.exit(terraform_result[1])
    # Delete VPCs batches
    temp_state.nodebatch_delete(vpc=obj_name)
    # Set new state to be current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    log_ok('{0} {1!r} deleted successfully'.format(obj_kind.upper(), obj_name))
    return True


if __name__ == "__main__":
    delete_cmd()
