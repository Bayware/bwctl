from enum import Enum
from typing import Any


class ObjectKind(Enum):
    """Possible Kind values in batch"""
    BATCH = 'batch'
    FABRIC = 'fabric'
    NODEBATCH = 'nodebatch'
    ORCHESTRATOR = 'orchestrator'
    PROCESSOR = 'processor'
    WORKLOAD = 'workload'
    VPC = 'vpc'


class ObjectState(Enum):
    """Possible object state"""
    DELETING = 'deleting'
    CONFIGURED = 'configured'
    STARTED = 'started'
    STOPPED = 'stopped'
    CREATED = 'created'
    UPDATED = 'updated'

    @classmethod
    def has_value(cls, value):
        return any(value == item.value for item in cls)


class ObjectStatus(Enum):
    """Possible object status"""
    FAILED = 'failed'
    SUCCESS = 'success'

    @classmethod
    def has_value(cls, value):
        return any(value == item.value for item in cls)


class Result:
    """Operation result status"""
    def __init__(self, status: bool = False, value: Any = None):
        """Initialise all attributes"""
        self.status: bool = status
        self.value: Any = value

    def __repr__(self) -> str:
        """"String reputation of an object"""
        return u"{} {}".format(self.status, self.value)
