#!/usr/bin/env bash

readonly SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
readonly CONTEXT_DIR="$( cd $SCRIPT_DIR/../.. >/dev/null 2>&1 && pwd )"
readonly ROOT_DIR="$( cd $CONTEXT_DIR/../../../.. >/dev/null 2>&1 && pwd )"
source ${CONTEXT_DIR}/.env

COMMANDS=docker
IFS=',' read -a commands <<< ${COMMANDS}
for COMMAND in ${commands[@]}; do
    if ! command -v ${COMMAND} &> /dev/null; then
        echo "Command could not be found: ${COMMAND}"
        exit 1
    fi
done

set -e
set -x

docker build \
    -t ${DEV_IMAGE_BASE} \
    -f $ROOT_DIR/Dockerfile \
    $ROOT_DIR