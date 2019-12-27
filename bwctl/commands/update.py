import sys
from copy import deepcopy

import click
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_info, log_warn
from bwctl.utils.states import ObjectKind, ObjectState


@click.group('update', cls=AliasedGroup)
def update_cmd():
    """Update commands"""
    pass


@update_cmd.command('workload')
@click.pass_context
@click.argument('workload-name', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
def update_workload(ctx, workload_name, dry_run, all_nodes):
    """Update workload"""
    obj_kind = ObjectKind.WORKLOAD.value
    obj_list, obj_name = None, None
    temp_state = deepcopy(ctx.obj.state)
    # Check if fabric is set
    if not temp_state.get_current_fabric():
        log_error('Cannot update {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check target objects to be used
    if all_nodes:
        if workload_name:
            log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                       temp_state.check_object_state(x[1], ObjectState.CREATED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                        temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created]
        if not obj_list:
            states = [ObjectState.CONFIGURED.value, ObjectState.UPDATED.value, ObjectState.STARTED.value,
                      ObjectState.STOPPED.value]
            log_error("Cannot update. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created:
            log_warn('There are {}s in created state: {!r}. Skipping...'.format(obj_kind.lower(), obj_created))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
    elif workload_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, workload_name)
        # Check if exist
        if not temp_state.check_workload(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot update. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, obj_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED):
            log_error("Cannot proceed, object is not configured")
            sys.exit(1)
        obj_list = [workload_name]
    elif workload_name is None:
        log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Update dry-run
    if dry_run:
        log_warn('{0}s to be updated: {1!r} (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    log_info('{0}s to be updated: {1!r}'.format(obj_kind.title(), obj_list))
    # Get action list
    actions_list = temp_state.update_actions_list(obj_kind, obj_list)
    if actions_list['update']:
        ansible_playbook = "update-workload.yml"
        res = temp_state.obj_update(ansible_playbook, obj_kind, actions_list['update'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['config']:
        res = temp_state.workload_configure(temp_state.get_current_fabric(), actions_list['config'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['stop']:
        res = temp_state.workload_stop(temp_state.get_current_fabric(), actions_list['stop'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['start']:
        res = temp_state.workload_start(temp_state.get_current_fabric(), actions_list['start'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    return True


@update_cmd.command('processor')
@click.pass_context
@click.argument('processor-name', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
def update_processor(ctx, processor_name, dry_run, all_nodes):
    """Update processor"""
    obj_kind = ObjectKind.PROCESSOR.value
    obj_list, obj_name = None, None
    temp_state = deepcopy(ctx.obj.state)
    # Check if fabric is set
    if not temp_state.get_current_fabric():
        log_error('Cannot update {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check target objects to be used
    if all_nodes:
        if processor_name:
            log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                       temp_state.check_object_state(x[1], ObjectState.CREATED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                        temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created]
        if not obj_list:
            states = [ObjectState.CONFIGURED.value, ObjectState.UPDATED.value, ObjectState.STARTED.value,
                      ObjectState.STOPPED.value]
            log_error("Cannot update. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created:
            log_warn('There are {}s in created state: {!r}. Skipping...'.format(obj_kind.lower(), obj_created))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
    elif processor_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, processor_name)
        # Check if exist
        if not temp_state.check_processor(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot update. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, obj_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED):
            log_error("Cannot proceed, object is not configured")
            sys.exit(1)
        obj_list = [processor_name]
    elif processor_name is None:
        log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Update dry-run
    if dry_run:
        log_warn('{0}s to be updated: {1!r} (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    log_info('{0}s to be updated: {1!r}'.format(obj_kind.title(), obj_list))
    # Get action list
    actions_list = temp_state.update_actions_list(obj_kind, obj_list)
    if actions_list['update']:
        ansible_playbook = "update-processor.yml"
        res = temp_state.obj_update(ansible_playbook, obj_kind, actions_list['update'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['config']:
        res = temp_state.processor_configure(temp_state.get_current_fabric(), actions_list['config'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['stop']:
        res = temp_state.processor_stop(temp_state.get_current_fabric(), actions_list['stop'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    temp_state = deepcopy(ctx.obj.state)
    if actions_list['start']:
        res = temp_state.processor_start(temp_state.get_current_fabric(), actions_list['start'])
        ctx.obj.state = deepcopy(temp_state)
        ctx.obj.state.dump()
        if not res[0]:
            sys.exit(res[1])
    return True


@update_cmd.command('orchestrator')
@click.pass_context
@click.argument('orchestrator-name', default=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
def update_orchestrator(ctx, orchestrator_name, dry_run, all_nodes):
    """Update orchestrator"""
    obj_kind = ObjectKind.ORCHESTRATOR.value
    obj_list, obj_name = None, None
    temp_state = deepcopy(ctx.obj.state)
    # Check if fabric is set
    if not temp_state.get_current_fabric():
        log_error('Cannot update {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check target objects to be used
    if all_nodes:
        if orchestrator_name:
            log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_all = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items()]
        obj_created = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                       temp_state.check_object_state(x[1], ObjectState.CREATED)]
        obj_deleting = [x[0] for x in temp_state.get_fabric_objects(obj_kind).items() if
                        temp_state.check_object_state(x[1], ObjectState.DELETING)]
        obj_list = [x for x in obj_all if x not in obj_deleting and x not in obj_created]
        if not obj_list:
            states = [ObjectState.CONFIGURED.value, ObjectState.UPDATED.value]
            log_error("Cannot update. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
        if obj_created:
            log_warn('There are {}s in created state: {!r}. Skipping...'.format(obj_kind.lower(), obj_created))
        if obj_deleting:
            log_warn('There are {}s in deleting state: {!r}. Skipping...'.format(obj_kind.lower(), obj_deleting))
        if not obj_list:
            states = [ObjectState.CREATED.value, ObjectState.CONFIGURED.value, ObjectState.UPDATED.value]
            log_error("Cannot update. There are no {}s in states: {!r}".format(obj_kind, states))
            sys.exit(1)
    elif orchestrator_name:
        # Check if naming matches rules
        obj_name = temp_state.normalise_state_obj_name(obj_kind, orchestrator_name)
        # Check if exist
        if not temp_state.check_orchestrator(temp_state.get_current_fabric(), obj_name):
            log_error("Cannot update. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = temp_state.get_fabric_object(obj_kind, orchestrator_name)
        if temp_state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if temp_state.check_object_state(obj, ObjectState.CREATED):
            log_error("Cannot proceed, object is not configured")
            sys.exit(1)
        obj_list = [orchestrator_name]
    elif orchestrator_name is None:
        log_error("Cannot update. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Update dry-run
    if dry_run:
        log_warn('{0}s {1!r} to be updated (used with --dry-run)'.format(obj_kind.title(), obj_list))
        return True
    # Update orchestrator
    log_info('{0}s to be updated: {1!r}'.format(obj_kind.title(), obj_list))
    ansible_playbook = "update-orchestrator.yml"
    res = temp_state.obj_update(ansible_playbook, obj_kind, obj_list)
    # Set temp state to current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    return True


if __name__ == "__main__":
    update_cmd()
