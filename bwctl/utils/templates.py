import os

from jinja2 import Environment, PackageLoader, StrictUndefined


# TODO: Refactor functions below to a class
def generate_from_template(state, fabric, hosted_zone, pub_key, cloud_storage, fabric_manager, username, aws_ec2_role,
                           file_name):
    """Generate terraform definition from Jinja2 template"""
    templates_dir_path = os.path.join('templates', 'terraform')
    jinja_env = Environment(
        loader=PackageLoader('bwctl', templates_dir_path),
        autoescape=True,
        trim_blocks=True,
        undefined=StrictUndefined)
    gen_content = jinja_env.get_template(file_name).render(state=state, fabric=fabric, hosted_zone=hosted_zone,
                                                           pub_key=pub_key, cloud_storage=cloud_storage,
                                                           fabric_manager=fabric_manager, username=username,
                                                           aws_ec2_role=aws_ec2_role)
    return gen_content


def generate_export_spec_from_template(fabric, current_fabric_name, api_version, file_name):
    """Generate export spec definition from Jinja2 template"""
    templates_dir_path = os.path.join('templates', 'export')

    # Custom functions
    def datetimenow():
        """Return current date & time"""
        from datetime import datetime
        return datetime.now().strftime('%a %b %_d %H:%M:%S %Y')

    jinja_env = Environment(
        loader=PackageLoader('bwctl', templates_dir_path),
        autoescape=True,
        lstrip_blocks=True,
        trim_blocks=True,
        undefined=StrictUndefined)

    # Add custom functions
    jinja_env.globals['datetimenow'] = datetimenow

    gen_content = jinja_env.get_template(file_name).render(fabric=fabric, current_fabric_name=current_fabric_name,
                                                           api_version=api_version)
    return gen_content


def generate_ssh_config_from_template(state, hosted_zone, username):
    """Generate ssh config from Jinja2 template"""
    templates_dir_path = os.path.join('templates', 'ssh')
    jinja_env = Environment(
        loader=PackageLoader('bwctl', templates_dir_path),
        autoescape=True,
        trim_blocks=True,
        undefined=StrictUndefined)
    gen_content = jinja_env.get_template('config.j2').render(state=state, hosted_zone=hosted_zone, username=username)
    return gen_content
