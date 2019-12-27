"""bwctl: 'start' commands implementation"""
import sys
from copy import deepcopy

import click

from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_info, log_warn
from bwctl.utils.states import ObjectKind, ObjectStatus, ObjectState


@click.group('start', cls=AliasedGroup)
def start_cmd():
    """Start commands"""


@start_cmd.command('workload')
@click.pass_context
@click.argument('workload-name', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
def start_workload(ctx, workload_name, dry_run, all_nodes):
    """Start workload"""
    obj_kind = ObjectKind.WORKLOAD.value
    obj_list, obj_name = None, None
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot start {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check target objects to be used
    if all_nodes:
        if workload_name:
            log_error("Cannot start. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_list = [x[0] for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if
                    not ctx.obj.state.check_object_state(x[1], ObjectState.DELETING) and
                    not ctx.obj.state.check_object_state(x[1], ObjectState.CREATED)]
        if not obj_list:
            log_error("Cannot start. There are no configured {}s".format(obj_kind))
            sys.exit(1)
    elif workload_name:
        # Check if naming matches rules
        obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, workload_name)
        # Check if exist
        if not ctx.obj.state.check_workload(ctx.obj.state.get_current_fabric(), obj_name):
            log_error("Cannot start. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = ctx.obj.state.get_fabric_object(obj_kind, obj_name)
        if ctx.obj.state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if ctx.obj.state.check_object_state(obj, ObjectState.STARTED) and \
                ctx.obj.state.check_object_status(obj, ObjectStatus.SUCCESS):
            log_warn("{0} {1!r} is already started".format(obj_kind.title(), obj_name))
            return True
        if not ctx.obj.state.check_object_state(obj, [ObjectState.CONFIGURED, ObjectState.STOPPED]):
            log_error("Cannot start. {0} {1!r} should be configured".format(obj_kind.title(), obj_name))
            sys.exit(1)
        obj_list = [workload_name]
    elif workload_name is None:
        log_error("Cannot start. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Start dry-run
    if dry_run:
        log_warn('{0} {1!r} to be started (used with --dry-run)'.format(obj_kind.title(), obj_name))
        return True
    log_info('{0}s to be started: {1!r}'.format(obj_kind.title(), obj_list))
    # Start action
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.workload_start(temp_state.get_current_fabric(), obj_list)
    # Set temp state to current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    return True


@start_cmd.command('processor')
@click.pass_context
@click.argument('processor-name', required=False)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
@click.option('--all', 'all_nodes', required=False, is_flag=True, default=False, show_default=True)
def start_processor(ctx, processor_name, dry_run, all_nodes):
    """Start processor"""
    obj_kind = ObjectKind.PROCESSOR.value
    obj_list, obj_name = None, None
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot start {0}. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check target objects to be used
    if all_nodes:
        if processor_name:
            log_error("Cannot start. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
            sys.exit(1)
        obj_list = [x[0] for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if
                    not ctx.obj.state.check_object_state(x[1], ObjectState.DELETING) and
                    not ctx.obj.state.check_object_state(x[1], ObjectState.CREATED)]
        if not obj_list:
            log_error("Cannot start. There are no configured {}s".format(obj_kind))
            sys.exit(1)
    elif processor_name:
        # Check if naming matches rules
        obj_name = ctx.obj.state.normalise_state_obj_name(obj_kind, processor_name)
        # Check if exist
        if not ctx.obj.state.check_processor(ctx.obj.state.get_current_fabric(), obj_name):
            log_error("Cannot start. {0} {1!r} doesn't exist".format(obj_kind.title(), obj_name))
            sys.exit(1)
        # Check state
        obj = ctx.obj.state.get_fabric_object(obj_kind, obj_name)
        if ctx.obj.state.check_object_state(obj, ObjectState.DELETING):
            log_error("Cannot proceed, object is set for deletion!")
            sys.exit(1)
        if ctx.obj.state.check_object_state(obj, ObjectState.STARTED) and \
                ctx.obj.state.check_object_status(obj, ObjectStatus.SUCCESS):
            log_warn("{0} {1!r} is already started".format(obj_kind.title(), obj_name))
            return True
        if not ctx.obj.state.check_object_state(obj, [ObjectState.CONFIGURED, ObjectState.STOPPED]):
            log_error("Cannot start. {0} {1!r} should be configured".format(obj_kind.title(), obj_name))
            sys.exit(1)
        obj_list = [processor_name]
    elif processor_name is None:
        log_error("Cannot start. Either {}-NAME or option --all should be used".format(obj_kind.upper()))
        sys.exit(1)
    # Start dry-run
    if dry_run:
        log_warn('{0} {1!r} to be started (used with --dry-run)'.format(obj_kind.title(), obj_name))
        return True
    log_info('{0}s to be started: {1!r}'.format(obj_kind.title(), obj_list))
    # Start action
    temp_state = deepcopy(ctx.obj.state)
    res = temp_state.processor_start(temp_state.get_current_fabric(), obj_list)
    # Set temp state to current and dump it
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    return True


if __name__ == "__main__":
    start_cmd()
