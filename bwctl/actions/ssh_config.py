import os

from bwctl.session.state import State
from bwctl.utils.common import dump_to_file
from bwctl.utils.templates import generate_ssh_config_from_template


class SshConfig:
    """SSH config configuration"""

    def __init__(self, state: State):
        """Initialise all attributes"""
        self.hosted_zone = state.config.get_attr('hosted_zone')
        self.state = state.get()
        self.out_file = os.path.join(os.path.expanduser("~/"), '.ssh/config')
        self.username = state.config.get_attr('username')

    def generate_config(self):
        """Generate ssh config file from template and dump it to file"""
        ssh_config_out = generate_ssh_config_from_template(self.state, self.hosted_zone, self.username)
        return dump_to_file(self.out_file, ssh_config_out)
