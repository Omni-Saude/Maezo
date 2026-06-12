"""
Teste de conectividade SMB a partir de um container Docker.
Grava um arquivo .txt no share de rede para validar que o container
Linux nativo consegue alcançar o servidor de arquivos do Tasy.

Uso (dentro do container):
    python test_smb_write.py

Variáveis de ambiente necessárias:
    SMB_HOST      - IP/hostname do servidor (default: 172.20.255.13)
    SMB_SHARE     - Nome do share          (default: tasyausta)
    SMB_PATH      - Pasta dentro do share  (default: anexo_opme)
    SMB_USER      - Usuário SMB            (ex: intensicarerobo.rpa)
    SMB_PASSWORD  - Senha SMB
    SMB_DOMAIN    - Domínio AD             (ex: AUSTA)  ← necessário se conta é de domínio
    SMB_PORT      - Porta SMB              (default: 445)
"""

import os
import sys
import socket
from datetime import datetime


def check_tcp(host: str, port: int, timeout: int = 5) -> bool:
    """Testa conectividade TCP pura (sem SMB)."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"  [TCP] {host}:{port} -> FALHOU ({e})")
        return False


def test_smb_write():
    host = os.environ.get("SMB_HOST", "172.20.255.13")
    share = os.environ.get("SMB_SHARE", "tasyausta")
    path = os.environ.get("SMB_PATH", "anexo_opme")
    user = os.environ.get("SMB_USER", "")
    password = os.environ.get("SMB_PASSWORD", "")
    domain = os.environ.get("SMB_DOMAIN", "")
    port = int(os.environ.get("SMB_PORT", "445"))

    # Se o usuário veio no formato DOMINIO\usuario ou usuario@dominio, extrair
    if not domain and "\\" in user:
        domain, user = user.split("\\", 1)
    elif not domain and "@" in user:
        user, domain = user.rsplit("@", 1)

    print("=" * 60)
    print("TESTE SMB A PARTIR DO DOCKER")
    print("=" * 60)
    print(f"  Host:     {host}")
    print(f"  Porta:    {port}")
    print(f"  Share:    {share}")
    print(f"  Path:     {path}")
    print(f"  Domínio:  {domain or '(nenhum - local)'}")
    print(f"  Usuário:  {user or '(vazio - anônimo)'}")
    print(f"  Horário:  {datetime.now().isoformat()}")
    print()

    # ── Etapa 1: Teste TCP ──
    print("[1/4] Testando conectividade TCP...")
    if not check_tcp(host, port):
        print()
        print("RESULTADO: FALHOU na conectividade TCP.")
        print("O container NÃO consegue alcançar o servidor.")
        print("Verifique: roteamento, VPN, Security Groups, firewall.")
        sys.exit(1)
    print(f"  [TCP] {host}:{port} -> OK")
    print()

    # ── Etapa 2: Importar smbclient ──
    print("[2/4] Importando smbclient...")
    try:
        import smbclient
        print(f"  smbclient importado com sucesso")
    except ImportError:
        print("  ERRO: smbprotocol não instalado. Execute: pip install smbprotocol")
        sys.exit(1)
    print()

    # ── Etapa 3: Registrar sessão SMB ──
    print("[3/4] Autenticando no share SMB...")
    try:
        # smbclient.register_session aceita username no formato DOMAIN\user
        smb_user = f"{domain}\\{user}" if domain else user
        smbclient.register_session(
            host,
            username=smb_user,
            password=password,
            port=port,
        )
        print(f"  Sessão registrada como: {smb_user}")
    except Exception as e:
        print(f"  ERRO na autenticação SMB: {e}")
        sys.exit(1)
    print()

    # ── Etapa 4: Gravar arquivo de teste ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hostname = socket.gethostname()
    filename = f"TESTE_DOCKER_{hostname}_{timestamp}.txt"
    remote_file = f"\\\\{host}\\{share}\\{path}\\{filename}"

    conteudo = (
        f"Arquivo de teste criado por container Docker\n"
        f"Hostname container: {hostname}\n"
        f"Data/hora: {datetime.now().isoformat()}\n"
        f"Servidor SMB: {host}\n"
        f"Share: {share}\n"
        f"Domínio: {domain or '(local)'}\n"
        f"Usuário: {user}\n"
        f"\n"
        f"Se você está lendo isto, o container Docker conseguiu\n"
        f"gravar no share de rede com sucesso!\n"
    )

    print(f"[4/4] Gravando arquivo: {remote_file}")
    try:
        with smbclient.open_file(remote_file, mode="w") as f:
            f.write(conteudo)
        print(f"  Gravação -> OK")
    except Exception as e:
        print(f"  ERRO ao gravar: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("RESULTADO: SUCESSO!")
    print(f"Arquivo criado: {remote_file}")
    print("O container Docker CONSEGUE gravar no share de rede.")
    print("=" * 60)


if __name__ == "__main__":
    if not os.environ.get("SMB_USER"):
        print("AVISO: SMB_USER não definido. Defina as variáveis de ambiente:")
        print("  export SMB_USER=seu_usuario")
        print("  export SMB_PASSWORD=sua_senha")
        print("  export SMB_DOMAIN=DOMINIO  (se conta for de domínio AD)")
        print()
        resp = input("Continuar sem credenciais? (s/N): ").strip().lower()
        if resp != "s":
            sys.exit(0)

    test_smb_write()
