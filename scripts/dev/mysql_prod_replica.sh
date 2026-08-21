#!/usr/bin/env bash
# Sobe um MySQL descartavel com o dump de producao carregado, para ensaiar a
# migracao no MESMO dialeto que a producao roda (nao no SQLite do dev).
#
# Nao encosta na instancia MySQL do Homebrew que o usuario ja tem rodando:
# datadir proprio, porta 3399, socket curto (o limite do socket e 103 chars).
#
#   scripts/dev/mysql_prod_replica.sh up   <dump.sql>   # inicia e carrega
#   scripts/dev/mysql_prod_replica.sh load <dump.sql>   # recarrega do zero
#   scripts/dev/mysql_prod_replica.sh cli               # abre o cliente
#   scripts/dev/mysql_prod_replica.sh down              # derruba
#
# URI para o app:  mysql+pymysql://root@127.0.0.1:3399/projetosRj

set -euo pipefail

MYSQL_HOME=${MYSQL_HOME:-/opt/homebrew/opt/mysql@8.4}
PORT=3399
SOCKET=/tmp/mysql3399.sock
DB=projetosRj
RUNDIR=${MYSQL_REPLICA_DIR:-/tmp/projetosrj-mysql-replica}

mysql_cli() { "$MYSQL_HOME/bin/mysql" -h 127.0.0.1 -P "$PORT" -u root "$@"; }

wait_up() {
  for _ in $(seq 1 60); do
    if mysql_cli -e "select 1" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  echo "ERRO: servidor nao subiu; veja $RUNDIR/error.log" >&2
  tail -20 "$RUNDIR/error.log" >&2 || true
  return 1
}

start_server() {
  if mysql_cli -e "select 1" >/dev/null 2>&1; then
    echo "ja no ar em 127.0.0.1:$PORT"
    return 0
  fi
  if [ ! -d "$RUNDIR/data/mysql" ]; then
    rm -rf "$RUNDIR"
    mkdir -p "$RUNDIR"
    "$MYSQL_HOME/bin/mysqld" --initialize-insecure \
      --datadir="$RUNDIR/data" --basedir="$MYSQL_HOME" 2>&1 | grep -i error || true
  fi
  nohup "$MYSQL_HOME/bin/mysqld" \
    --datadir="$RUNDIR/data" --basedir="$MYSQL_HOME" \
    --port="$PORT" --socket="$SOCKET" --mysqlx=OFF \
    --pid-file="$RUNDIR/mysqld.pid" --log-error="$RUNDIR/error.log" \
    >/dev/null 2>&1 &
  wait_up
  echo "no ar: 127.0.0.1:$PORT (mysqld $("$MYSQL_HOME/bin/mysqld" --version | awk '{print $3}'))"
}

load_dump() {
  local dump=$1
  [ -f "$dump" ] || { echo "ERRO: dump nao encontrado: $dump" >&2; exit 1; }
  mysql_cli -e "drop database if exists \`$DB\`;
                create database \`$DB\` character set utf8mb4 collate utf8mb4_0900_ai_ci;"
  mysql_cli "$DB" < "$dump"
  mysql_cli "$DB" -e "select (select count(*) from user) users,
                             (select count(*) from project) projects,
                             (select version_num from alembic_version) revisao;"
}

case "${1:-}" in
  up)   start_server; load_dump "${2:?informe o caminho do dump .sql}" ;;
  load) start_server; load_dump "${2:?informe o caminho do dump .sql}" ;;
  cli)  mysql_cli "$DB" ;;
  down)
    if [ -f "$RUNDIR/mysqld.pid" ]; then
      kill "$(cat "$RUNDIR/mysqld.pid")" 2>/dev/null || true
      echo "derrubado"
    else
      echo "nada rodando"
    fi
    ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
