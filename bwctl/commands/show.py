"""bwctl: 'show' commands implementation"""
import json
import sys
from collections import OrderedDict

import click

from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_info
from bwctl.utils.states import ObjectKind


@click.group('show', cls=AliasedGroup)
def show_cmd():
    """Show commands"""


@show_cmd.command('workload')
@click.pass_context
@click.option('--name', required=False, default=None)
@click.option('--cloud', type=click.Choice(['azr', 'aws', 'gcp', 'all']), required=False, default='all')
@click.option('--full', required=False, is_flag=True, default=False, show_default=True)
def show_workload(ctx, name, cloud, full):
    """Show workload information"""
    obj_kind = ObjectKind.WORKLOAD.value
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot show {0} contents. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    if name is not None:
        name = ctx.obj.state.normalise_state_obj_name(obj_kind, name)
    # Initialise workload object
    workload_obj = []
    # If workload name set
    if name is not None:
        # If name set - always show full info
        full = True

        # Check workload existence
        if not ctx.obj.state.check_workload(ctx.obj.state.get_current_fabric(), name):
            log_error("Cannot show. {0} {1!r} doesn't exist".format(obj_kind.title(), name))
            sys.exit(1)

        # If no filter by cloud
        if cloud == 'all':
            workload_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if name in x[0]]

        # If filter by cloud
        if cloud != 'all':
            workload_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                            if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                                obj_kind, x[0])['vpc'])['cloud'] and name in x[0]]

            # Empty result set
            if not workload_obj:
                log_error("Cannot show. {0} {1!r} isn't in {2!r} cloud".format(obj_kind.title(), name, cloud))
                sys.exit(1)
    # If name not set
    else:
        # If filter by cloud
        if cloud != 'all':
            workload_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                            if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                                obj_kind, x[0])['vpc'])['cloud']]

            # Empty result set
            if not workload_obj:
                log_error("Cannot show. No {0} in {1!r} cloud".format(obj_kind, cloud))
                sys.exit(1)

        # If no filter by cloud
        else:
            workload_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()]
            # Empty result set
            if not workload_obj:
                log_error("Cannot show. No {0} in {1!r} cloud".format(obj_kind, cloud))
                sys.exit(1)

    # Output
    if full:
        if name is not None:
            click.secho('{0} {1!s}:'.format(obj_kind.title(), name), fg='green')
        else:
            click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        click.echo(json.dumps(dict(workload_obj), indent=2))
        return True
    else:
        click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        for obj in workload_obj:
            click.echo('{0:15s}'.format(obj[0]))
        return True


@show_cmd.command('processor')
@click.pass_context
@click.option('--name', required=False, default=None)
@click.option('--cloud', type=click.Choice(['azr', 'aws', 'gcp', 'all']), required=False, default='all')
@click.option('--full', required=False, is_flag=True, default=False, show_default=True)
def show_processor(ctx, name, cloud, full):
    """Show processor information"""
    obj_kind = ObjectKind.PROCESSOR.value
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot show {0} contents. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    if name is not None:
        name = ctx.obj.state.normalise_state_obj_name(obj_kind, name)
    # Initialise processor object
    processor_obj = []
    # If processor name set
    if name is not None:
        # If name set - always show full info
        full = True

        # Check processor existence
        if not ctx.obj.state.check_processor(ctx.obj.state.get_current_fabric(), name):
            log_error("Cannot show. {0} {1!r} doesn't exist".format(obj_kind.title(), name))
            sys.exit(1)

        # If no filter by cloud
        if cloud == 'all':
            processor_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if name in x[0]]

        # If filter by cloud
        if cloud != 'all':
            processor_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                             if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                    obj_kind, x[0])['vpc'])['cloud'] and name
                             in x[0]]

            # Empty result set
            if not processor_obj:
                log_error("Cannot show. {0} {1!r} isn't in {2!r} cloud".format(obj_kind.title(), name, cloud))
                sys.exit(1)
    # If name not set
    else:
        # If filter by cloud
        if cloud != 'all':
            processor_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                             if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                                obj_kind, x[0])['vpc'])['cloud']]

            # Empty result set
            if not processor_obj:
                log_error("Cannot show. No {0} in {1!r} cloud".format(obj_kind, cloud))
                sys.exit(1)

        # If no filter by cloud
        else:
            processor_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()]

    # Output
    if full:
        if name is not None:
            click.secho('{0} {1!s}:'.format(obj_kind.title(), name), fg='green')
        else:
            click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        click.echo(json.dumps(dict(processor_obj), indent=2))
        return True
    else:
        click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        for obj in processor_obj:
            click.echo('{0:15s}'.format(obj[0]))
        return True


@show_cmd.command('fabric')
@click.option('--list-all', required=False, is_flag=True, default=False, show_default=True)
@click.option('--name', required=False, default=None)
@click.pass_context
def show_fabric(ctx, list_all, name):
    """Show fabric information"""
    fabric_key_order = ['state', 'status', 'config', 'vpc', 'orchestrator', 'processor', 'workload']
    current_fabric = ctx.obj.state.get_current_fabric()
    # If list_all - just list and end
    if list_all:
        click.echo('{:1s} {:15s}'.format(' ', 'FABRIC'))
        for fabric_key in ctx.obj.state.get().get('fabric'):
            click.echo(
                '{0:^1s} {1:15s}'.format('*' if fabric_key == current_fabric else ' ', fabric_key))
        return True
    # Check if fabric is set
    if name is not None:
        # Check existence
        if not ctx.obj.state.check_fabric(name):
            log_error("Cannot show. Fabric {0!r} doesn't exist".format(name))
            sys.exit(1)
        fabric_name = name
    else:
        if not current_fabric:
            log_info('Available fabrics listed.  Use “bwctl set fabric FABRIC_NAME” to select fabric.')
            click.echo('{:1s} {:15s}'.format(' ', 'FABRIC'))
            for fabric_key in ctx.obj.state.get().get('fabric'):
                click.echo(
                    '{0:^1s} {1:15s}'.format('*' if fabric_key == current_fabric else ' ', fabric_key))
            sys.exit(1)
        fabric_name = current_fabric
    # List dict in defined order
    fabric_state = OrderedDict()
    for key in fabric_key_order:
        if key in ctx.obj.state.get_fabric(fabric_name):
            fabric_state[key] = ctx.obj.state.get_fabric(fabric_name)[key]
    click.echo('{0!s}:'.format(current_fabric))
    click.echo(json.dumps(fabric_state, indent=2))
    return True


@show_cmd.command('orchestrator')
@click.pass_context
@click.option('--name', required=False, default=None)
@click.option('--cloud', type=click.Choice(['azr', 'aws', 'gcp', 'all']), required=False, default='all')
@click.option('--full', required=False, is_flag=True, default=False, show_default=True)
def show_orchestrator(ctx, name, cloud, full):
    """Show orchestrator information"""
    obj_kind = ObjectKind.ORCHESTRATOR.value
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot show {0} contents. Please select fabric first.'.format(obj_kind))
        sys.exit(1)
    # Check if naming matches rules
    if name is not None:
        name = ctx.obj.state.normalise_state_obj_name(obj_kind, name)
    # Initialise orchestrator object
    orchestrator_obj = []
    # If orchestrator name set
    if name is not None:
        # If name set - always show full info
        full = True

        # Check orchestrator existence
        if not ctx.obj.state.check_orchestrator(ctx.obj.state.get_current_fabric(), name):
            log_error("Cannot show. {0} {1!r} doesn't exist".format(obj_kind.title(), name))
            sys.exit(1)

        # If no filter by cloud
        if cloud == 'all':
            orchestrator_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if name in x[0]]

        # If filter by cloud
        if cloud != 'all':
            orchestrator_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                                if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                                    obj_kind, x[0])['vpc'])['cloud'] and name in x[0]]

            # Empty result set
            if not orchestrator_obj:
                log_error("Cannot show. {0} {1!r} isn't in {2!r} cloud".format(obj_kind.title(), name, cloud))
                sys.exit(1)
    # If name not set
    else:
        # If filter by cloud
        if cloud != 'all':
            orchestrator_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()
                                if cloud in ctx.obj.state.get_fabric_object('vpc', ctx.obj.state.get_fabric_object(
                                    obj_kind, x[0])['vpc'])['cloud']]

            # Empty result set
            if not orchestrator_obj:
                log_error("Cannot show. No {0} in {1!r} cloud".format(obj_kind, cloud))
                sys.exit(1)

        # If no filter by cloud
        else:
            orchestrator_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()]

    # Output
    if full:
        if name is not None:
            click.secho('{0} {1!s}:'.format(obj_kind.title(), name), fg='green')
        else:
            click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        click.echo(json.dumps(dict(orchestrator_obj), indent=2))
        return True
    else:
        click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        for obj in orchestrator_obj:
            click.echo('{0:15s}'.format(obj[0]))
        return True


@show_cmd.command('vpc')
@click.pass_context
@click.option('--name', required=False, default=None)
@click.option('--cloud', type=click.Choice(['azr', 'aws', 'gcp', 'all']), required=False, default='all')
@click.option('--full', required=False, is_flag=True, default=False, show_default=True)
@click.option('--regions', is_flag=True, required=False, default=False, show_default=True)
def show_vpc(ctx, name, cloud, full, regions):
    """Show VPC information"""
    obj_kind = ObjectKind.VPC.value
    if regions:
        if cloud != 'all':
            for x in ctx.obj.cloud_regions[cloud]:
                click.echo('{0!s}'.format(x))
        else:
            for x in ctx.obj.cloud_regions:
                click.echo('{0!s}:'.format(x))
                for y in ctx.obj.cloud_regions[x]:
                    click.echo('  {0!s}'.format(y))
        return True
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot show VPC contents. Please select fabric first.')
        sys.exit(1)
    # Check if naming matches rules
    if name is not None:
        name = ctx.obj.state.normalise_state_obj_name(obj_kind, name)
    # Initialise vpc object
    vpc_obj = []

    # If vpc name set
    if name is not None:
        # If name set - always show full info
        full = True

        # Check VPC existence
        if not ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), name):
            log_error("Cannot show. VPC {0!r} doesn't exist".format(name))
            sys.exit(1)

        # If no filter by cloud
        if cloud == 'all':
            vpc_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if name in x[0]]

        # If filter by cloud
        if cloud != 'all':
            vpc_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if cloud in x[1]['cloud']
                       and name in x[0]]
            # Empty result set
            if not vpc_obj:
                log_error("Cannot show. VPC {0!r} isn't in {1!r} cloud".format(name, cloud))
                sys.exit(1)
    # If name not set
    else:
        # If filter by cloud
        if cloud != 'all':
            vpc_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if cloud in x[1]['cloud']]
            # Empty result set
            if not vpc_obj:
                log_error("Cannot show. No VPC in {0!r} cloud".format(cloud))
                sys.exit(1)

        # If no filter by cloud
        else:
            vpc_obj = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items()]

    # Output
    if full:
        if name is not None:
            click.secho('{0} {1!s}:'.format(obj_kind.title(), name), fg='green')
        else:
            click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        click.echo(json.dumps(dict(vpc_obj), indent=2))
        return True
    else:
        click.secho("{0} list in {1!r} cloud".format(obj_kind.title(), cloud), fg='green')
        for obj in vpc_obj:
            click.echo('{0:15s}'.format(obj[0]))
        return True


if __name__ == "__main__":
    show_cmd()
