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
# TODO: Add actual testing

print_blu "\u21e8 pylint information"
pylint --version
print_blu "\u21e8 Run Python lint check"
# TODO: Add actual testing

print_blu "\u21e8 shellcheck information"
shellcheck --version
print_blu "\u21e8 Run shell scripts lint check"
# TODO: Add actual testing

print_blu "\u21e8 yamllint information"
yamllint --version
print_blu "\u21e8 Run shell scripts lint check"

# EOF
