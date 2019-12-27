import getpass
import sys
from datetime import datetime

import boto3
import click
import psutil
import yaml


def timestamp():
    """Return current time"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def log_color(msg, nl=True, fg=None):
    """Echo colored message to console prepended by timestamp"""
    click.secho('[{0!s}]  {1!s}'.format(timestamp(), msg), nl=nl, fg=fg)


def log_error(msg, nl=True):
    """Echo error message to console prepended by timestamp"""
    log_color(msg, nl=nl, fg='red')


def log_info(msg, nl=True):
    """Echo informational message to console prepended by timestamp"""
    log_color(msg, nl=nl)


def log_ok(msg, nl=True):
    """Echo positive result message to console prepended by timestamp"""
    log_color(msg, nl=nl, fg='green')


def log_warn(msg, nl=True):
    """Echo warning message to console prepended by timestamp"""
    log_color(msg, nl=nl, fg='yellow')


def dump_dict_to_file(out_file, data):
    """Dump dict to a file"""
    # noinspection PyBroadException
    try:
        with open(out_file, 'w') as dump_f:
            yaml.dump(data, dump_f, default_flow_style=False)
        dump_f.close()
    except IOError as dump_err:
        log_error("I/O error({}): {}".format(dump_err.errno, dump_err.strerror))
        return False
    except Exception:  # handle other exceptions such as attribute errors
        log_error("Unexpected error: {}".format(sys.exc_info()[0]))
        return False
    return True


def dump_dict_to_s3(attr, bucket, key, credentials):
    """Dump dict to s3 object"""
    s3_client = boto3.client('s3', aws_access_key_id=credentials.get_aws_param('aws_access_key_id').value,
                             aws_secret_access_key=credentials.get_aws_param('aws_secret_access_key').value)
    try:
        s3_client.put_object(Body=yaml.dump(attr, default_flow_style=False), Bucket=bucket, Key=key)
    except s3_client.exceptions.ClientError as dump_err:
        log_error("S3 error: {}".format(dump_err))
        return False
    log_ok("State uploaded successfully")
    return True


def dump_to_file(out_file, data):
    """Dump data to a file"""
    # noinspection PyBroadException
    try:
        with open(out_file, 'w') as out_f:
            out_f.write(data)
        out_f.close()
    except IOError as err:
        log_error("{0} - I/O error({1}): {2}".format(out_file, err.errno, err.strerror))
        return False
    except Exception as err:  # handle other exceptions such as attribute errors
        log_error("{0} - Unexpected error: {1} ({2})".format(out_file, sys.exc_info()[0], err))
        return False
    return True


def check_process_running(process_name):
    """Check if there is any running process with the given name"""
    current_user = getpass.getuser()
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name', 'username'])
            if process_name == pinfo['name'] and current_user == pinfo['username']:
                return True, pinfo['pid'], pinfo['username']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False, None, None
