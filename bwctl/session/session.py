"""
This module implements click session handling
"""

import os
import shutil
import sys
from typing import Dict

import bwctl.templates
import bwctl_resources.ansible
import bwctl_resources.terraform
import click
from bwctl.session.state import State
from bwctl.utils.common import log_info, log_error
from prompt_toolkit.history import FileHistory


class Session:
    """Define click session object"""

    def __init__(self):
        """Initialise all attributes"""
        # Initialise bwctl version
        self.version_file: str = '../version.txt'
        # noinspection PyBroadException
        try:
            with open(os.path.join(os.path.dirname(__file__), self.version_file)) as f:
                self.version = f.read().strip()
            f.close()
        except IOError as err:
            log_error("I/O error while reading {0!r} ({1!s}): {2!s}".format(self.version_file, err.errno, err.strerror))
        except Exception:
            log_error("Unexpected error while reading {0!r}: {1!s}".format(self.version_file, sys.exc_info()[0]))

        # Initialise Bayware family version
        self.version_family_file: str = '../version_family.txt'
        # noinspection PyBroadException
        try:
            with open(os.path.join(os.path.dirname(__file__), self.version_family_file)) as f:
                self.version_family = f.read().strip()
            f.close()
        except IOError as err:
            log_error("I/O error while reading {0!r} ({1!s}): {2!s}".format(self.version_family_file, err.errno,
                                                                            err.strerror))
        except Exception:  # handle other exceptions such as attribute errors
            log_error("Unexpected error while reading {0!r}: {1!s}".format(self.version_family_file, sys.exc_info()[0]))

        # Init state
        self.state = State(self.version, self.version_family)
        self.state.init()

        # File names
        self.history_file: str = os.path.join(self.state.config.dir, 'history')
        self.credentials_template_file: str = os.path.join(self.state.config.dir, 'credentials.yml')
        self.terraform_dir: str = os.path.join(self.state.config.dir, 'terraform')

        # Ensure terraform plan structures ready
        try:
            os.makedirs(self.terraform_dir)
        except FileExistsError:
            # directory already exists
            pass
        for entity in ['modules', 'resources']:
            src: str = os.path.join(os.path.dirname(bwctl_resources.terraform.__file__), entity)
            dst: str = os.path.join(self.terraform_dir, entity)
            try:
                os.symlink(src, dst)
            except FileExistsError:
                # link already exists
                pass

        # Initialise repl
        self.default_prompt_msg: str = u"bwctl> "
        self.prompt_kwargs: Dict = {
            "history": FileHistory(self.history_file),
            "message": self.default_prompt_msg,
            "complete_while_typing": True,
            "enable_history_search": True
        }

        # Initialise supported regions
        self.cloud_regions: Dict = {
            'aws': [
                'ap-east-1',
                'ap-northeast-1',
                'ap-northeast-2',
                'ap-south-1',
                'ap-southeast-1',
                'ap-southeast-2',
                'ca-central-1',
                'eu-central-1',
                'eu-north-1',
                'eu-west-1',
                'eu-west-2',
                'eu-west-3',
                'sa-east-1',
                'us-east-1',
                'us-east-2',
                'us-west-1',
                'us-west-2'
            ],
            'azr': [
                'centralus',
                'eastus',
                'eastus2',
                'japaneast',
                'southcentralus',
                'westeurope',
                'westus',
                'westus2'
            ],
            'gcp': [
                'asia-east1',
                'asia-east2',
                'asia-northeast1',
                'asia-northeast2',
                'asia-south1',
                'asia-southeast1',
                'australia-southeast1',
                'europe-north1',
                'europe-west1',
                'europe-west2',
                'europe-west3',
                'europe-west4',
                'europe-west6',
                'northamerica-northeast1',
                'southamerica-east1',
                'us-central1',
                'us-east1',
                'us-east4',
                'us-west1',
                'us-west2'
            ]
        }

    def __repr__(self) -> str:
        """"String reputation of an object"""
        return u"{}".format(self.cloud_regions)

    def do_version(self) -> bool:
        """Print bwctl version"""
        click.echo(self.version)
        return True

    def init_credentials_template(self) -> bool:
        """Check and copy credentials template"""
        src_credentials_file_name = os.path.join(os.path.dirname(bwctl.templates.__file__), 'credentials.yml')
        if not os.path.exists(self.credentials_template_file):
            log_info("No credentials file template found, copying clean...")
            shutil.copyfile(src_credentials_file_name, self.credentials_template_file)
        return True

    def set_cli_prefix(self):
        """"Set REPL prompt prefix to current fabric"""
        self.prompt_kwargs['message'] = u"({0}) {1}".format(self.state.get_current_fabric(),
                                                            self.default_prompt_msg)

    def set_current_fabric(self, fabric: str) -> bool:
        """Set current fabric name"""
        res: bool = self.state.config.set_attr('current_fabric', fabric)
        if res:
            self.set_cli_prefix()
        return res
