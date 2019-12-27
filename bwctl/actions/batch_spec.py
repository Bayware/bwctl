from bwctl.utils.common import log_info
from bwctl.utils.states import ObjectKind


class BatchSpec(object):
    """Batch helper object"""

    def __init__(self, batch, api_version):
        """Initialise all attributes"""
        self.batch = batch

        # Is it batch?
        if not (bool(self.batch['kind']) and self.batch['kind'].lower() == ObjectKind.BATCH.value):
            raise TypeError("This is not a batch")

        self.bwctl_api_version = api_version
        self.batch_api_version = self.batch.get('apiVersion')
        self.batch_metadata = self.batch.get('metadata')
        self.batch_spec = self.batch.get('spec')
        self.spec = dict()
        for i in self.batch_spec:
            if i['kind'].lower() in self.spec:
                self.spec[i['kind'].lower()].append(i)
            else:
                self.spec[i['kind'].lower()] = [i]
        log_info(
            "Found batch {0!r} ({1!s}) with {2!s} objects".format(self.batch_metadata['name'],
                                                                  self.batch_metadata['description'],
                                                                  len(self.batch_spec)))
        # TODO: Handle wrong format

    def add_to_attr_list(self, attr, value):
        """Add batch value to attribute list"""
        if attr is not None and type(attr) == ObjectKind:
            if attr.value in self.spec:
                self.spec[attr.value].append(value)
            else:
                self.spec[attr.value] = [value]

    def check_batch_version(self):
        """Check batch API version and bwctl API version"""
        if self.bwctl_api_version != self.batch_api_version:
            return False
        else:
            return True

    def get_attr_list(self, attr):
        """Get batch attribute list"""
        if attr is not None and type(attr) == ObjectKind:
            return [elem for key, value in self.spec.items() if key == attr.value for elem in value]
        return None

    @staticmethod
    def get_attr_name(attr):
        if attr.get('metadata'):
            return attr['metadata'].get('name') or None
        return None
