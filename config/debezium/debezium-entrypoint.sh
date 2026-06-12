#!/bin/bash
# Lê os secrets do Docker Swarm (/run/secrets/) e exporta como variáveis de ambiente
# antes de iniciar o processo principal do Debezium/Kafka Connect.

set -e

if [ -f /run/secrets/aws_access_key_id ]; then
  export AWS_ACCESS_KEY_ID=$(cat /run/secrets/aws_access_key_id)
fi

if [ -f /run/secrets/aws_secret_access_key ]; then
  export AWS_SECRET_ACCESS_KEY=$(cat /run/secrets/aws_secret_access_key)
fi

exec /docker-entrypoint.sh "$@"
