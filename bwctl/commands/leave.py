"""bwctl: 'leave' commands implementation"""
import sys

import click

from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_info, log_error


@click.group('leave', cls=AliasedGroup)
def leave_cmd():
    """Leave commands"""


@leave_cmd.command('fabric')
@click.pass_context
def leave_fabric(ctx):
    """Leave current fabric"""
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot leave. Please select fabric first.')
        sys.exit(1)
    log_info('Leaving fabric {0!r}'.format(ctx.obj.state.get_current_fabric()))
    return ctx.obj.set_current_fabric(None)


if __name__ == "__main__":
    leave_cmd()
