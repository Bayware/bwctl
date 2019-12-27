#!/usr/bin/env bash
#
# Run various tests

# Write safe shell scripts
set -euf -o pipefail

# Set locale to US UTF-8
export LC_ALL="en_US.UTF-8"

# Set the colours
readonly C_NOC="\033[0m"    # No colour
readonly C_RED="\033[0;31m" # Red
readonly C_GRN="\033[0;32m" # Green
readonly C_BLU="\033[0;34m" # Blue

# Helper functions
print_red () { local i; for i in "$@"; do echo -e "${C_RED}${i}${C_NOC}"; done }
print_grn () { local i; for i in "$@"; do echo -e "${C_GRN}${i}${C_NOC}"; done }
print_blu () { local i; for i in "$@"; do echo -e "${C_BLU}${i}${C_NOC}"; done }

# Run tests
print_blu "\u21e8 ansible-lint information"
ansible-lint --version
print_blu "\u21e8 Run ansible playbooks lint check"
find ./ -name '*.yml' -print0 | /usr/bin/env xargs -0 -t -n1 ansible-lint -v -p --force-color -x 204  -r ./tests/ansible-lint-custom-rules/ -R

print_blu "\u21e8 pylint information"
pylint --version
print_blu "\u21e8 Run Python lint check"
find ./ -name '*.py' -print0 | /usr/bin/env xargs -0 -t -n1 pylint --rcfile=./tests/pylintrc

print_blu "\u21e8 shellcheck information"
shellcheck --version
print_blu "\u21e8 Run shell scripts lint check"
find ./ -name "*.sh" -print0 | /usr/bin/env xargs -0 -t -n1 shellcheck -s bash

print_blu "\u21e8 yamllint information"
yamllint --version
print_blu "\u21e8 Run shell scripts lint check"
find ./ -name '*.yml' -print0 | /usr/bin/env xargs -0 -t -n1 yamllint -c ./tests/yaml-lint-custom-rules/yaml_lint_custom.yml

# EOF
