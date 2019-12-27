#!/usr/bin/env bash

set -ef -o pipefail
readonly BASE_DIR="$(dirname "$(realpath "$0")")" 
readonly BWCTL_HOME="$HOME/.bwctl"

# Terraform
if [[ ! -d "$BWCTL_HOME/terraform" ]]; then
    mkdir -p "$BWCTL_HOME/terraform"
fi
# Purge templates and copy fresh
find "$BWCTL_HOME/terraform" -maxdepth 1 -mindepth 1 ! -type d -exec rm -rf {} \;
while read -r i; do
    find "$i" -maxdepth 1 -mindepth 1 ! -name "\.terraform" ! -name "terraform.tfstate*" -exec rm -rf {} \;
done < <(find "$BWCTL_HOME/terraform" -maxdepth 1 -mindepth 1 -type d)

if [[ ! -d "./venv/" ]]; then
    virtualenv --python=python3 venv
    # shellcheck disable=SC1091
    # motivation: ./venv/bin... does not exist before exec virtualenv
    source ./venv/bin/activate
    pip install --editable .
    pip install --editable ../bwctl_resources
else
    # shellcheck disable=SC1091
    # motivation: ./venv/bin... does not exist before exec virtualenv
    source ./venv/bin/activate
fi

#find . -name "*.pyc" -exec rm -f {} \;

bwctl "$@"
