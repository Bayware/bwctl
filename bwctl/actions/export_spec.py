from bwctl.utils.common import dump_to_file
from bwctl.utils.templates import generate_export_spec_from_template


class ExportSpec:
    """Export batch specification"""

    def __init__(self, fabric=None, fabric_name=None, export_format=None, out_file=None, api_version=None):
        """Initialise all attributes"""
        self.export_format = export_format.lower()
        if export_format not in ['yaml', 'json']:
            raise ValueError("Export format should be 'yaml' or 'json'")
        self.fabric = fabric
        self.fabric_name = fabric_name
        self.out_file = out_file
        self.api_version = api_version
        self.BATCH_SPEC_TEMPLATES = {
            'yaml': 'export.yaml',
            'json': 'export.json'
        }
        self.batch_spec_template = self.BATCH_SPEC_TEMPLATES[self.export_format]

    def generate_spec(self):
        """Generate spec file from template and dump it to file"""
        export_out = generate_export_spec_from_template(self.fabric, self.fabric_name, self.api_version,
                                                        self.batch_spec_template + '.j2')
        return dump_to_file(self.out_file, export_out)
