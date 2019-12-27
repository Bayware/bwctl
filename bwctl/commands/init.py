"""bwctl: 'init' command implementation"""
import re

import click
from bwctl.utils.common import log_info, log_ok


def request_validate_bool(value):
    """Validate answer bool"""
    valid = {"true": True, "True": True, "false": False, "False": False}
    if value in valid:
        return True, valid[value]
    return False, None


def request_validate_str(value, regexp=None):
    """Validate answer to match regexp"""
    if regexp is None:
        regexp = "^[a-zA-Z0-9-]+$"
    pattern = re.compile(regexp)
    if not pattern.match(value):
        log_info("Please respond with value that match pattern {!r}".format(regexp))
        return False, None
    return True, value


def request_config_parameter_str(message, default=None, regexp=None):
    """Requires answer with string value"""
    if default is None:
        prompt = " (value is required): "
    else:
        prompt = " [{}]: ".format(default)
    while True:
        log_info(message + prompt, nl=False)
        choice = input().lower()
        if default is None and choice == "":
            continue
        if default is not None and choice == "":
            return default
        if request_validate_str(choice, regexp)[0]:
            return request_validate_str(choice, regexp)[1]
        else:
            pass


def request_config_parameter_bool(message, default=False):
    """Requires answer with true/false"""
    prompt = " [{}]: ".format(str(default).lower())
    while True:
        log_info(message + prompt, nl=False)
        choice = input().lower()
        if choice == "":
            return default
        elif request_validate_bool(choice)[0]:
            return request_validate_bool(choice)[1]
        else:
            pass


@click.command('init')
@click.option('--show-hidden', required=False, is_flag=True, default=False, show_default=True)
@click.pass_context
def init_cmd(ctx, show_hidden):
    """Init bwctl configuration"""
    log_info("Welcome to bwctl initialization")
    # Init fabric manager configuration
    log_info("Fabric manager")
    attr_key = 'fabric_manager'
    attr_val = ctx.obj.state.config.get_attr(attr_key)
    company_name_default = None
    if bool(attr_val['company_name']):
        company_name_default = attr_val['company_name']
    attr_val['company_name'] = request_config_parameter_str(" Company name", company_name_default)
    ctx.obj.state.config.set_attr(attr_key, attr_val, override=True)
    # Init global configuration
    log_info("Global")
    attr_val = ctx.obj.state.config.get_attr('credentials_file')
    attr_val = request_config_parameter_str(" Cloud providers credentials file", attr_val,
                                            regexp="^[a-zA-Z0-9-_~.# ]+$")
    ctx.obj.state.config.set_attr('credentials_file', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_attr('hosted_zone')
    attr_val = request_config_parameter_str(" DNS hosted zone", attr_val, regexp="^[a-zA-Z0-9-.]+$")
    ctx.obj.state.config.set_attr('hosted_zone', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_debug()
    attr_val = request_config_parameter_bool(" Debug enabled", attr_val)
    ctx.obj.state.config.set_attr('debug', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_attr('production')
    attr_val = request_config_parameter_bool(" Production mode enabled", attr_val)
    ctx.obj.state.config.set_attr('production', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_attr('marketplace')
    attr_val = request_config_parameter_bool(" Marketplace images to be used", attr_val)
    ctx.obj.state.config.set_attr('marketplace', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_attr('os_type')
    attr_val = request_config_parameter_str(" Preffered workload's image OS type", attr_val, regexp="^[a-z]+$")
    ctx.obj.state.config.set_attr('os_type', attr_val, override=True)
    attr_val = ctx.obj.state.config.get_attr('username')
    attr_val = request_config_parameter_str(" Administrative OS account", attr_val, regexp="^[a-zA-Z0-9-_]+$")
    ctx.obj.state.config.set_attr('username', attr_val, override=True)
    # Init components configuration
    log_info("Components")
    attr_key = 'components'
    attr_val = ctx.obj.state.config.get_attr(attr_key)
    if show_hidden:
        attr_val['branch'] = request_config_parameter_str(" Branch", attr_val['branch'])
    attr_val['family'] = request_config_parameter_str(" Family version", attr_val['family'], regexp="^[0-9.]+$")
    ctx.obj.state.config.set_attr(attr_key, attr_val, override=True)
    # Init cloud storage configuration
    log_info("Cloud storage")
    attr_key = 'cloud_storage'
    attr_val = ctx.obj.state.config.get_attr(attr_key)
    attr_val['state']['enabled'] = request_config_parameter_bool(" Store bwctl state on AWS S3",
                                                                 attr_val['state']['enabled'])
    if attr_val['state']['enabled']:
        attr_val['state']['bucket'] = request_config_parameter_str("  AWS S3 bucket name", attr_val['state']['bucket'])
        attr_val['state']['region'] = request_config_parameter_str("  AWS region", attr_val['state']['region'])
    attr_val['terraform']['enabled'] = request_config_parameter_bool(" Store terraform state on AWS S3",
                                                                     attr_val['terraform']['enabled'])
    if attr_val['terraform']['enabled']:
        attr_val['terraform']['bucket'] = request_config_parameter_str("  AWS S3 bucket name",
                                                                       attr_val['terraform']['bucket'])
        attr_val['terraform']['region'] = request_config_parameter_str("  AWS region", attr_val['terraform']['region'])
    ctx.obj.state.config.set_attr(attr_key, attr_val, override=True)
    # Init SSH keys configuration
    log_info("SSH keys")
    attr_key = 'ssh_keys'
    attr_val = ctx.obj.state.config.get_attr(attr_key)
    attr_val['private_key'] = request_config_parameter_str(" SSH Private key file", attr_val['private_key'],
                                                           regexp="^[a-zA-Z0-9-_~.# ]+$")
    ctx.obj.state.config.set_attr(attr_key, attr_val, override=True)
    log_ok('Configuration is done')
    return True


if __name__ == "__main__":
    init_cmd()
