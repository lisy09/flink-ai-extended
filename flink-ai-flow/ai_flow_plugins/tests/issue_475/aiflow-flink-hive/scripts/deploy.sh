#!/usr/bin/env bash

readonly SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
CONTEXT_DIR="$( cd $SCRIPT_DIR/.. >/dev/null 2>&1 && pwd )"
ROOT_DIR="$( cd $CONTEXT_DIR/../../../.. >/dev/null 2>&1 && pwd )"

set -e
set -x

if [ "$(docker network ls -f name=app -q)" = "" ]; then 
    docker network create app; 
fi
cd ${ROOT_DIR}
CONTEXT_DIR=${CONTEXT_DIR} \
ROOT_DIR=${ROOT_DIR} \
docker compose \
    --env-file=${CONTEXT_DIR}/.env \
    -f ${CONTEXT_DIR}/docker-compose.yml up -d