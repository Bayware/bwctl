"""bwctl: 'set' commands implementation"""
import sys

import click

from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_ok, log_warn
from bwctl.utils.states import ObjectStatus, ObjectState


@click.group(name='set', cls=AliasedGroup)
def set_cmd():
    """Set commands"""


@set_cmd.command('fabric')
@click.pass_context
@click.argument('fabric-name')
def set_fabric(ctx, fabric_name):
    """Set current fabric"""
    # Check fabric exists
    if not ctx.obj.state.check_fabric(fabric_name):
        log_error("Fabric {!r} doesn't exist".format(fabric_name))
        sys.exit(1)
    fabric = ctx.obj.state.get_fabric(fabric_name)
    # Check fabric state and status
    if ctx.obj.state.check_object_state(fabric, ObjectState.DELETING):
        log_warn("Proceeding, but object is set for deletion!")
        ctx.obj.set_current_fabric(fabric_name)
        log_ok('Active fabric: {0!r}'.format(fabric_name))
        return True
    if not ctx.obj.state.check_object_state(fabric, ObjectState.CONFIGURED) or \
            not ctx.obj.state.check_object_status(fabric, ObjectStatus.SUCCESS):
        log_error("Cannot activate, configure fabric {0!r} first".format(fabric_name))
        sys.exit(1)
    else:
        ctx.obj.set_current_fabric(fabric_name)
        log_ok('Active fabric: {0!r}'.format(fabric_name))
        return True


if __name__ == "__main__":
    set_cmd()
