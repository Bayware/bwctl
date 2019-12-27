#!/usr/bin/env bash
#
# This is temporary init script for bwctl data

if [[ "$0" = "${BASH_SOURCE[0]}" ]]; then
    echo "Do not execute the script, source it instead: . $0"
    exit 1
fi

BASE_DIR=$(dirname "${BASH_SOURCE[0]}")

export ANSIBLE_VAULT_PASSWORD_FILE="${HOME}/ansible_secrets/vault_bayware_terraform_pass.txt"
cd "$BASE_DIR/../resources" || return
./decrypt.sh
# shellcheck disable=SC1091
. ./setenv
cd - || return
