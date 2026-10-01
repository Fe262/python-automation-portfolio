"""
Banco de dados (SQLite: um arquivo .db, nao precisa instalar nada).

Tabelas:
    servicos      -> o que o estabelecimento oferece (nome, duracao, preco)
    agendamentos  -> cada horario marcado por um cliente
"""
import secrets
import sqlite3
from datetime import datetime

from flask import current_app, g

ESQUEMA = """
CREATE TABLE IF NOT EXISTS servicos (
    id          INTEGER PRIMARY KEY,
    nome        TEXT    NOT NULL,
    duracao_min INTEGER NOT NULL,
    preco       REAL    NOT NULL,
    ativo       INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS agendamentos (
    id         INTEGER PRIMARY KEY,
    servico_id INTEGER NOT NULL REFERENCES servicos(id),
    cliente    TEXT    NOT NULL,
    telefone   TEXT    NOT NULL,
    inicio     TEXT    NOT NULL,  -- data e hora no formato 2026-10-05T14:30
    fim        TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'marcado',  -- marcado, concluido ou cancelado
    codigo     TEXT    NOT NULL UNIQUE,  -- codigo aleatorio do comprovante (nao da para adivinhar)
    criado_em  TEXT    NOT NULL
);
"""

SERVICOS_EXEMPLO = [
    ("Corte de cabelo", 30, 45.0),
    ("Barba", 30, 30.0),
    ("Corte + barba", 60, 70.0),
    ("Coloração", 90, 120.0),
]

FORMATO = "%Y-%m-%dT%H:%M"


def conectar() -> sqlite3.Connection:
    """Uma conexao por requisicao (o Flask guarda em "g")."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # permite usar linha["nome"] em vez de linha[1]
    return g.db


def fechar(_erro=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def criar_tabelas(com_exemplos: bool = True) -> None:
    db = conectar()
    db.executescript(ESQUEMA)
    vazio = db.execute("SELECT COUNT(*) FROM servicos").fetchone()[0] == 0
    if com_exemplos and vazio:
        db.executemany("INSERT INTO servicos (nome, duracao_min, preco) VALUES (?, ?, ?)", SERVICOS_EXEMPLO)
    db.commit()


# ---------- Servicos ----------

def listar_servicos(somente_ativos: bool = True):
    sql = "SELECT * FROM servicos" + (" WHERE ativo = 1" if somente_ativos else "") + " ORDER BY nome"
    return conectar().execute(sql).fetchall()


def buscar_servico(servico_id: int):
    return conectar().execute("SELECT * FROM servicos WHERE id = ?", (servico_id,)).fetchone()


def criar_servico(nome: str, duracao_min: int, preco: float) -> None:
    db = conectar()
    db.execute("INSERT INTO servicos (nome, duracao_min, preco) VALUES (?, ?, ?)", (nome, duracao_min, preco))
    db.commit()


def alternar_servico(servico_id: int) -> None:
    """Ativa/desativa (nao apaga, para nao estragar agendamentos antigos)."""
    db = conectar()
    db.execute("UPDATE servicos SET ativo = 1 - ativo WHERE id = ?", (servico_id,))
    db.commit()


# ---------- Agendamentos ----------

def ocupados_no_dia(dia_iso: str) -> list[tuple[datetime, datetime]]:
    """Horarios ja tomados naquele dia (cancelados nao contam)."""
    linhas = conectar().execute(
        "SELECT inicio, fim FROM agendamentos WHERE inicio LIKE ? AND status != 'cancelado'",
        (dia_iso + "%",)).fetchall()
    return [(datetime.strptime(l["inicio"], FORMATO), datetime.strptime(l["fim"], FORMATO)) for l in linhas]


def criar_agendamento(servico_id: int, cliente: str, telefone: str,
                      inicio: datetime, fim: datetime) -> str | None:
    """Grava o agendamento e devolve o codigo do comprovante.
    Devolve None se o horario foi pego por outra pessoa.

    O comprovante usa um codigo aleatorio, e nao o numero 1, 2, 3...: com numeros,
    qualquer um trocaria o endereco e veria nome e telefone de outros clientes.

    "BEGIN IMMEDIATE" trava o banco durante a conferencia + gravacao: assim duas
    pessoas clicando no mesmo horario ao mesmo tempo nao conseguem marcar as duas.
    """
    db = conectar()
    db.execute("BEGIN IMMEDIATE")
    conflito = db.execute(
        "SELECT 1 FROM agendamentos WHERE status != 'cancelado' AND inicio < ? AND fim > ?",
        (fim.strftime(FORMATO), inicio.strftime(FORMATO))).fetchone()
    if conflito:
        db.rollback()
        return None
    codigo = secrets.token_urlsafe(9)
    db.execute(
        """INSERT INTO agendamentos (servico_id, cliente, telefone, inicio, fim, codigo, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (servico_id, cliente, telefone, inicio.strftime(FORMATO), fim.strftime(FORMATO),
         codigo, datetime.now().strftime(FORMATO)))
    db.commit()
    return codigo


def buscar_agendamento(agendamento_id: int):
    return conectar().execute(
        """SELECT a.*, s.nome AS servico, s.preco FROM agendamentos a
           JOIN servicos s ON s.id = a.servico_id WHERE a.id = ?""", (agendamento_id,)).fetchone()


def buscar_por_codigo(codigo: str):
    return conectar().execute(
        """SELECT a.*, s.nome AS servico, s.preco FROM agendamentos a
           JOIN servicos s ON s.id = a.servico_id WHERE a.codigo = ?""", (codigo,)).fetchone()


def listar_agendamentos(dia_iso: str):
    return conectar().execute(
        """SELECT a.*, s.nome AS servico, s.preco FROM agendamentos a
           JOIN servicos s ON s.id = a.servico_id
           WHERE a.inicio LIKE ? ORDER BY a.inicio""", (dia_iso + "%",)).fetchall()


def mudar_status(agendamento_id: int, status: str) -> None:
    db = conectar()
    db.execute("UPDATE agendamentos SET status = ? WHERE id = ?", (status, agendamento_id))
    db.commit()
