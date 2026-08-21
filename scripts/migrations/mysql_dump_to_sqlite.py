"""Converte um dump mysqldump para um arquivo SQLite.

Escopo deliberadamente estreito: cobre o subconjunto de DDL usado pelo dump de
producao do projetosRj (25 tabelas, sem views/procs/triggers/generated cols).
"""

from __future__ import annotations

import re
import sqlite3
import sys

MYSQL_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "%": "\\%",
    "_": "\\_",
}


def strip_directives(sql: str) -> str:
    sql = re.sub(r"/\*!\d+\s(.*?)\*/;", "", sql, flags=re.S)
    sql = re.sub(r"/\*!\d+\s?", "", sql)
    sql = sql.replace("*/", "")
    return sql


def split_top_level(body: str) -> list[str]:
    """Quebra o miolo do CREATE TABLE em itens, respeitando parenteses/aspas."""
    parts, depth, buf, quote = [], 0, [], None
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            buf.append(ch)
            if ch == "\\":
                i += 1
                if i < len(body):
                    buf.append(body[i])
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


TYPE_MAP = [
    (r"^tinyint\(1\)", "INTEGER"),
    (r"^(tiny|small|medium|big)?int(\(\d+\))?", "INTEGER"),
    (r"^(var)?char\(\d+\)", "TEXT"),
    (r"^(long|medium|tiny)?text", "TEXT"),
    (r"^(long|medium|tiny)?blob", "BLOB"),
    (r"^varbinary\(\d+\)", "BLOB"),
    (r"^decimal\([\d,\s]+\)", "NUMERIC"),
    (r"^(float|double)(\([\d,\s]+\))?", "REAL"),
    (r"^datetime(\(\d+\))?", "DATETIME"),
    (r"^timestamp(\(\d+\))?", "DATETIME"),
    (r"^date\b", "DATE"),
    (r"^time\b", "TIME"),
    (r"^json\b", "TEXT"),
    (r"^enum\(.*?\)", "TEXT"),
]


def convert_column(item: str, single_int_pk: str | None) -> str:
    match = re.match(r"^`(?P<name>[^`]+)`\s+(?P<rest>.*)$", item, flags=re.S)
    if not match:
        raise ValueError(f"coluna nao reconhecida: {item!r}")
    name, rest = match["name"], match["rest"].strip()

    sqlite_type = None
    for pattern, replacement in TYPE_MAP:
        hit = re.match(pattern, rest, flags=re.I)
        if hit:
            sqlite_type = replacement
            rest = rest[hit.end() :].strip()
            break
    if sqlite_type is None:
        raise ValueError(f"tipo nao mapeado em: {item!r}")

    rest = re.sub(r"\bCOMMENT\s+'(?:[^'\\]|\\.)*'", "", rest, flags=re.I)
    rest = re.sub(r"\bCHARACTER SET \w+", "", rest, flags=re.I)
    rest = re.sub(r"\bCOLLATE [\w]+", "", rest, flags=re.I)
    rest = re.sub(r"\bunsigned\b", "", rest, flags=re.I)
    rest = re.sub(r"\bON UPDATE CURRENT_TIMESTAMP(\(\d*\))?", "", rest, flags=re.I)
    rest = re.sub(r"\bAUTO_INCREMENT\b", "", rest, flags=re.I)
    rest = re.sub(
        r"\bDEFAULT\s+CURRENT_TIMESTAMP(\(\d*\))?", "DEFAULT CURRENT_TIMESTAMP", rest, flags=re.I
    )
    rest = re.sub(r"\s+", " ", rest).strip()

    if name == single_int_pk:
        # SQLite so aceita autoincrement em INTEGER PRIMARY KEY.
        rest = re.sub(r"\bNOT NULL\b", "", rest, flags=re.I).strip()
        return f'"{name}" INTEGER PRIMARY KEY AUTOINCREMENT {rest}'.strip()
    return f'"{name}" {sqlite_type} {rest}'.strip()


def convert_create_table(stmt: str) -> tuple[str, list[tuple[str, str, str, bool]]]:
    head = re.match(
        r"CREATE TABLE `(?P<table>[^`]+)` \((?P<body>.*)\)[^)]*$", stmt, flags=re.S
    )
    if not head:
        raise ValueError(f"CREATE TABLE nao reconhecido: {stmt[:120]!r}")
    table, body = head["table"], head["body"]
    items = split_top_level(body)

    pk_cols: list[str] = []
    for item in items:
        pk = re.match(r"^PRIMARY KEY \((?P<cols>.*?)\)", item, flags=re.I)
        if pk:
            pk_cols = re.findall(r"`([^`]+)`", pk["cols"])
    auto_col = None
    for item in items:
        if re.search(r"AUTO_INCREMENT", item, flags=re.I) and item.startswith("`"):
            auto_col = re.match(r"^`([^`]+)`", item)[1]
    single_int_pk = auto_col if (auto_col and pk_cols == [auto_col]) else None

    columns: list[str] = []
    constraints: list[str] = []
    indexes: list[tuple[str, str, str, bool]] = []

    for item in items:
        upper = item.upper()
        if upper.startswith("PRIMARY KEY"):
            if single_int_pk is None and pk_cols:
                cols = ", ".join(f'"{c}"' for c in pk_cols)
                constraints.append(f"PRIMARY KEY ({cols})")
            continue
        if upper.startswith("UNIQUE KEY"):
            hit = re.match(r"^UNIQUE KEY `(?P<name>[^`]+)` \((?P<cols>.*?)\)$", item, flags=re.I | re.S)
            cols = ", ".join(f'"{c}"' for c in re.findall(r"`([^`]+)`", hit["cols"]))
            indexes.append((hit["name"], table, cols, True))
            continue
        if upper.startswith("KEY ") or upper.startswith("FULLTEXT KEY"):
            hit = re.match(r"^(?:FULLTEXT )?KEY `(?P<name>[^`]+)` \((?P<cols>.*?)\)$", item, flags=re.I | re.S)
            if hit is None:
                continue
            cols = ", ".join(f'"{c}"' for c in re.findall(r"`([^`]+)`", hit["cols"]))
            indexes.append((hit["name"], table, cols, False))
            continue
        if upper.startswith("CONSTRAINT"):
            hit = re.match(
                r"^CONSTRAINT `[^`]+` FOREIGN KEY \((?P<cols>.*?)\) "
                r"REFERENCES `(?P<ref>[^`]+)` \((?P<refcols>.*?)\)(?P<actions>.*)$",
                item,
                flags=re.I | re.S,
            )
            if hit is None:
                continue
            cols = ", ".join(f'"{c}"' for c in re.findall(r"`([^`]+)`", hit["cols"]))
            refcols = ", ".join(f'"{c}"' for c in re.findall(r"`([^`]+)`", hit["refcols"]))
            actions = re.sub(r"\s+", " ", hit["actions"] or "").strip()
            constraints.append(
                f'FOREIGN KEY ({cols}) REFERENCES "{hit["ref"]}" ({refcols}) {actions}'.strip()
            )
            continue
        columns.append(convert_column(item, single_int_pk))

    inner = ",\n  ".join(columns + constraints)
    return f'CREATE TABLE "{table}" (\n  {inner}\n);', indexes


def parse_insert(stmt: str) -> tuple[str, list[list[object]]]:
    hit = re.match(r"INSERT INTO `(?P<table>[^`]+)` VALUES ", stmt, flags=re.I)
    if not hit:
        raise ValueError(f"INSERT nao reconhecido: {stmt[:120]!r}")
    table = hit["table"]
    payload = stmt[hit.end() :]

    rows: list[list[object]] = []
    row: list[object] = []
    buf: list[str] = []
    in_string = False
    depth = 0
    i = 0
    while i < len(payload):
        ch = payload[i]
        if in_string:
            if ch == "\\":
                nxt = payload[i + 1]
                buf.append(MYSQL_ESCAPES.get(nxt, nxt))
                i += 2
                continue
            if ch == "'":
                if i + 1 < len(payload) and payload[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_string = False
                row.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_string = True
            buf = []
            i += 1
            continue
        if ch == "(":
            depth += 1
            buf = []
            i += 1
            continue
        if ch in ",)":
            token = "".join(buf).strip()
            if token:
                row.append(None if token.upper() == "NULL" else _number(token))
            buf = []
            if ch == ")":
                depth -= 1
                rows.append(row)
                row = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    return table, rows


def _number(token: str) -> object:
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def iter_statements(sql: str):
    buf: list[str] = []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        buf.append(ch)
        if quote:
            if ch == "\\":
                i += 1
                if i < len(sql):
                    buf.append(sql[i])
            elif ch == quote:
                quote = None
        elif ch in "'`\"":
            quote = ch
        elif ch == ";":
            yield "".join(buf[:-1]).strip()
            buf = []
        i += 1
    tail = "".join(buf).strip()
    if tail:
        yield tail


def main(dump_path: str, db_path: str) -> None:
    raw = open(dump_path, encoding="utf-8", errors="replace").read()
    raw = strip_directives(raw)
    raw = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("--")
    )

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    tables, inserted = 0, 0
    pending_indexes: list[tuple[str, str, str, bool]] = []

    for stmt in iter_statements(raw):
        if not stmt:
            continue
        upper = stmt.lstrip().upper()
        if upper.startswith("CREATE TABLE"):
            ddl, indexes = convert_create_table(stmt.strip())
            conn.execute(ddl)
            pending_indexes.extend(indexes)
            tables += 1
        elif upper.startswith("INSERT INTO"):
            table, rows = parse_insert(stmt.strip())
            if not rows:
                continue
            placeholders = ", ".join("?" * len(rows[0]))
            conn.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
            inserted += len(rows)
        elif upper.startswith(("DROP TABLE", "LOCK TABLES", "UNLOCK TABLES", "SET ", "USE ")):
            continue

    # Nome de indice e por-tabela no MySQL e global no SQLite: so prefixa em colisao,
    # para que as migrations que citam `ix_...` pelo nome continuem encontrando-o.
    used: set[str] = set()
    for name, table, cols, unique in pending_indexes:
        final = name if name not in used else f"{table}_{name}"
        used.add(final)
        kind = "UNIQUE INDEX" if unique else "INDEX"
        index_sql = f'CREATE {kind} "{final}" ON "{table}" ({cols});'
        try:
            conn.execute(index_sql)
        except sqlite3.OperationalError as exc:
            print(f"  aviso indice: {exc} -- {index_sql}")

    conn.commit()
    conn.close()
    print(f"tabelas={tables} linhas={inserted} -> {db_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
