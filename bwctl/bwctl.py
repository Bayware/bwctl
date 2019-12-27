import click
import click_repl
import os
import sys
from pid import PidFile, PidFileAlreadyLockedError
from bwctl.commands.configure import configure_cmd
from bwctl.commands.create import create_cmd
from bwctl.commands.delete import delete_cmd
from bwctl.commands.export import export_cmd
from bwctl.commands.init import init_cmd
from bwctl.commands.leave import leave_cmd
from bwctl.commands.restart import restart_cmd
from bwctl.commands.set import set_cmd
from bwctl.commands.show import show_cmd
from bwctl.commands.start import start_cmd
from bwctl.commands.stop import stop_cmd
from bwctl.commands.update import update_cmd
from bwctl.session.session import Session
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_error, log_info


@click.group(invoke_without_command=True, cls=AliasedGroup)
@click.option('-v', '--version', required=False, is_flag=True, default=False, help="Print version and exit.")
@click.pass_context
def bwctl(ctx, version):
    """Bayware CLI"""
    # Print version
    if version:
        ctx.obj.do_version()
        return True
    # Init credentials template
    if not ctx.obj.init_credentials_template():
        log_info("Exiting...")
        sys.exit(1)
    # Run REPL if no command has been passed
    if ctx.invoked_subcommand is None:
        ctx.obj.set_cli_prefix()
        ctx.invoke(repl)


@bwctl.command(name='help', add_help_option=False, hidden=True)
@click.pass_context
def do_help(ctx):
    """Print help"""
    click.echo(ctx.parent.get_help())


@bwctl.command(name='quit', add_help_option=False, hidden=True)
def do_quit():
    """Quit REPL"""
    raise click_repl.ExitReplException()


@click.pass_context
def repl(ctx):
    """Start the REPL"""
    click_repl.repl(ctx, prompt_kwargs=ctx.obj.prompt_kwargs, allow_system_commands=False,
                    allow_internal_commands=False)


def main():
    """Main function"""
    # Add commands
    bwctl.add_command(create_cmd)
    bwctl.add_command(configure_cmd)
    bwctl.add_command(delete_cmd)
    bwctl.add_command(export_cmd)
    bwctl.add_command(init_cmd)
    bwctl.add_command(leave_cmd)
    bwctl.add_command(restart_cmd)
    bwctl.add_command(set_cmd)
    bwctl.add_command(show_cmd)
    bwctl.add_command(start_cmd)
    bwctl.add_command(stop_cmd)
    bwctl.add_command(update_cmd)

    bwctl(
        obj=Session(),
        help_option_names=["-h", "--help"],
        max_content_width=120,
        auto_envvar_prefix="BW"
    )


# Handle bwctl PID locking
pidname = 'bwctl'
piddir = os.path.expanduser("~/.bwctl")
try:
    with PidFile(pidname, piddir=piddir) as p:
        main()
except PidFileAlreadyLockedError:
    log_error('Lock detected, bwctl is already running. Exiting...')
    sys.exit(1)
except IOError:
    log_error('Unable to create lockfile {!r}, please check permissions. Exiting...'.format(os.path.join(piddir,
                                                                                                         pidname)))
    sys.exit(1)
