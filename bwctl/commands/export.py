"""bwctl: 'leave' commands implementation"""
import sys

import click

from bwctl.actions.export_spec import ExportSpec
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_ok, log_info


@click.group('export', cls=AliasedGroup)
def export_cmd():
    """Export commands"""


@export_cmd.command('fabric')
@click.pass_context
@click.argument('filename')
@click.option('--output-format', required=False, type=click.Choice(['json', 'yaml']), default='yaml', show_default=True)
def export_fabric(ctx, filename, output_format):
    """Export fabric specification to file"""
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error("Please set fabric before exporting")
        sys.exit(1)
    log_info('Exporting to {0!r}'.format(filename))
    export_spec = ExportSpec(fabric=ctx.obj.state.get_fabric(ctx.obj.state.get_current_fabric()),
                             fabric_name=ctx.obj.state.get_current_fabric(), export_format=output_format,
                             out_file=filename, api_version=ctx.obj.state.api_version)
    if export_spec.generate_spec():
        log_ok('Fabric configuration exported successfully')
        return True
    log_error('Error exporting fabric configuration')
    sys.exit(1)


if __name__ == "__main__":
    export_cmd()
