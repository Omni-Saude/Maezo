#!/bin/bash
# ============================================================
# Teste: Container Docker grava arquivo no share de rede Tasy
# ============================================================
#
# Uso:
#   chmod +x run_test.sh
#   ./run_test.sh
#
# Ou com credenciais inline:
#   SMB_USER=usuario SMB_PASSWORD=senha ./run_test.sh
#
# ============================================================

set -e

# ── Configurações (altere conforme seu ambiente) ──
SMB_HOST="${SMB_HOST:-172.20.255.13}"
SMB_SHARE="${SMB_SHARE:-tasyausta}"
SMB_PATH="${SMB_PATH:-anexo_opme}"
SMB_PORT="${SMB_PORT:-445}"

# ── Solicitar credenciais se não fornecidas ──
if [ -z "$SMB_DOMAIN" ]; then
    read -p "Domínio AD (ex: AUSTA, ou vazio se local): " SMB_DOMAIN
fi
if [ -z "$SMB_USER" ]; then
    read -p "Usuário SMB: " SMB_USER
fi
if [ -z "$SMB_PASSWORD" ]; then
    read -s -p "Senha SMB: " SMB_PASSWORD
    echo
fi

IMAGE_NAME="test-smb-docker"

echo ""
echo "=== Build da imagem de teste ==="
docker build -t "$IMAGE_NAME" "$(dirname "$0")"

echo ""
echo "=== Executando teste ==="
docker run --rm \
    -e SMB_HOST="$SMB_HOST" \
    -e SMB_SHARE="$SMB_SHARE" \
    -e SMB_PATH="$SMB_PATH" \
    -e SMB_PORT="$SMB_PORT" \
    -e SMB_DOMAIN="$SMB_DOMAIN" \
    -e SMB_USER="$SMB_USER" \
    -e SMB_PASSWORD="$SMB_PASSWORD" \
    "$IMAGE_NAME"

echo ""
echo "=== Imagem de teste pode ser removida com: docker rmi $IMAGE_NAME ==="
