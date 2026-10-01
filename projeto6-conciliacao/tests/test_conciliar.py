"""Testes da conciliacao. Rodar na pasta do projeto: python -m pytest -v"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from conciliar import (DUPLICADA, OK, SO_EMPRESA, SO_FUNCIONARIOS, VALOR_DIFERENTE,  # noqa: E402
                       adivinhar_coluna, conciliar, normalizar_os, para_numero)


def test_normalizar_os_aceita_formatos_baguncados():
    for bruto in ["OS-00123", "os 123", " 123 ", 123, 123.0, "O.S. 0123", "ORDEM: 123"]:
        assert normalizar_os(bruto) == "123", bruto


def test_para_numero_aceita_formato_brasileiro():
    assert para_numero("R$ 1.234,50") == 1234.5
    assert para_numero("150,00") == 150.0
    assert para_numero(99) == 99.0
    assert para_numero("abc") is None


def rodar(emp_linhas, func_linhas):
    emp = pd.DataFrame(emp_linhas, columns=["OS", "Valor"])
    func = pd.DataFrame(func_linhas, columns=["Nome", "OS", "Valor"])
    return conciliar(emp, func, "OS", "Valor", "OS", "Valor", "Nome")


def status_de(resultado, os):
    return resultado["Detalhe"].set_index("OS").loc[os, "Status"]


def test_todos_os_casos():
    r = rodar(
        [(1, 100), (2, 200), (3, 300), (4, 400)],
        [("Ana", "OS-1", "100,00"),     # ok
         ("Ana", "OS-2", "250,00"),     # valor diferente
         ("Bia", "OS-5", "500,00"),     # empresa nao pagou
         ("Bia", "OS-4", "400,00"),     # duplicada (Ana e Bia)
         ("Ana", "OS-4", "400,00")])    # OS 3: so na empresa
    assert status_de(r, "1") == OK
    assert status_de(r, "2") == VALOR_DIFERENTE
    assert status_de(r, "3") == SO_EMPRESA
    assert status_de(r, "5") == SO_FUNCIONARIOS
    assert set(r["Detalhe"][r["Detalhe"]["OS"] == "4"]["Status"]) == {DUPLICADA}


def test_tolerancia_de_centavos():
    r = rodar([(1, 100.0)], [("Ana", 1, 100.004)])
    assert status_de(r, "1") == OK


def test_resumo_por_funcionario():
    r = rodar([(1, 100), (2, 200)], [("Ana", 1, 100), ("Ana", 2, 250), ("Ana", 9, 50)])
    ana = r["Por funcionário"].set_index("Funcionário").loc["Ana"]
    assert ana["OS declaradas"] == 3
    assert ana["Valor declarado"] == 400
    assert ana["OS confirmadas"] == 2
    assert ana["Valor confirmado (empresa)"] == 300
    assert ana["Diferença"] == 100


def test_linhas_sem_os_sao_ignoradas():
    r = rodar([(1, 100), (None, 999)], [("Ana", 1, 100), ("Ana", None, 5)])
    assert len(r["Detalhe"]) == 1


def test_adivinhar_coluna():
    assert adivinhar_coluna(["Data", "Número OS", "Valor pago"], ["os"]) == 1
    assert adivinhar_coluna(["Técnico", "Ordem de serviço"], ["funcion", "técnico"]) == 0


def test_planilhas_de_exemplo():
    """As divergencias plantadas em gerar_exemplo.py precisam ser encontradas."""
    import subprocess
    pasta = Path(__file__).parent.parent
    subprocess.run([sys.executable, "gerar_exemplo.py"], cwd=pasta, check=True, capture_output=True)
    emp = pd.read_excel(pasta / "exemplo" / "empresa_setembro.xlsx")
    func = pd.read_excel(pasta / "exemplo" / "funcionarios_setembro.xlsx")
    r = conciliar(emp, func, "Número OS", "Valor pago", "Ordem de serviço", "Valor", "Técnico")
    contagem = r["Detalhe"].drop_duplicates(["OS", "Status"])["Status"].value_counts()
    assert contagem[VALOR_DIFERENTE] == 3
    assert contagem[SO_EMPRESA] == 2
    assert contagem[SO_FUNCIONARIOS] == 2
    assert contagem[DUPLICADA] == 1
