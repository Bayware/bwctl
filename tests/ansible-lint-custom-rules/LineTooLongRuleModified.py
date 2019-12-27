# pylint: skip-file
"""
Custom LineTooLongRule implementation
"""
from ansiblelint import AnsibleLintRule

class LineTooLongRuleModified(AnsibleLintRule):
    id = '299'
    shortdesc = 'Lines should be no longer than 200 chars'
    description = (
        'Long lines make code harder to read and '
        'code review more difficult.'
        'This check based on standart E204 test, just changed count of chars.'
    )
    severity = 'VERY_LOW'
    tags = ['formatting']
    version_added = 'v4.0.1'

    def match(self, file, line):
        return len(line) > 200
