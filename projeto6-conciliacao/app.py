"""
Tela da conciliacao: envie as duas planilhas, escolha as colunas e veja as divergencias.

Como rodar (na pasta do projeto):
    streamlit run app.py
"""
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from conciliar import (DUPLICADA, OK, SO_EMPRESA, SO_FUNCIONARIOS, VALOR_DIFERENTE,
                       adivinhar_coluna, conciliar)

st.set_page_config(page_title="Conciliação de OS", page_icon="🔎", layout="wide")
st.title("🔎 Conciliação de ordens de serviço")
st.caption("Compara a planilha da empresa com a planilha dos funcionários e mostra o que não bate.")

col1, col2 = st.columns(2)
arq_emp = col1.file_uploader("1. Planilha da EMPRESA (o que foi pago)", type=["xlsx", "xls", "csv"])
arq_func = col2.file_uploader("2. Planilha dos FUNCIONÁRIOS (produção)", type=["xlsx", "xls", "csv"])


def ler(arquivo) -> pd.DataFrame:
    return pd.read_csv(arquivo, sep=None, engine="python") if arquivo.name.endswith(".csv") else pd.read_excel(arquivo)


EXEMPLO = Path(__file__).parent / "exemplo"
if st.button("Ou use as planilhas de exemplo (dados inventados)"):
    st.session_state.exemplo = True

if arq_emp and arq_func:
    empresa, funcionarios = ler(arq_emp), ler(arq_func)
elif st.session_state.get("exemplo"):
    if not (EXEMPLO / "empresa_setembro.xlsx").exists():
        subprocess.run([sys.executable, "gerar_exemplo.py"], cwd=Path(__file__).parent, check=True)
    empresa = pd.read_excel(EXEMPLO / "empresa_setembro.xlsx")
    funcionarios = pd.read_excel(EXEMPLO / "funcionarios_setembro.xlsx")
else:
    st.info("Envie as duas planilhas para começar.")
    st.stop()

# Cada empresa usa nomes de coluna diferentes: o usuario escolhe (com sugestao automatica)
st.subheader("3. Quais colunas usar?")
c1, c2, c3, c4, c5 = st.columns(5)
ce, cf = list(empresa.columns), list(funcionarios.columns)
os_emp = c1.selectbox("Nº da OS (empresa)", ce, adivinhar_coluna(ce, ["os", "ordem", "número", "numero"]))
valor_emp = c2.selectbox("Valor (empresa)", ce, adivinhar_coluna(ce, ["valor", "preço", "total"]))
os_func = c3.selectbox("Nº da OS (funcionários)", cf, adivinhar_coluna(cf, ["os", "ordem", "número", "numero"]))
valor_func = c4.selectbox("Valor (funcionários)", cf, adivinhar_coluna(cf, ["valor", "preço", "total"]))
nome_func = c5.selectbox("Nome do funcionário", cf, adivinhar_coluna(cf, ["funcion", "técnico", "tecnico", "nome", "colaborador"]))

resultado = conciliar(empresa, funcionarios, os_emp, valor_emp, os_func, valor_func, nome_func)
detalhe = resultado["Detalhe"]

st.subheader("4. Resultado")
contagem = detalhe.drop_duplicates(["OS", "Status"])["Status"].value_counts()  # conta OS, nao linhas
m = st.columns(5)
for coluna, (status, rotulo) in zip(m, [(OK, "✅ OK"), (VALOR_DIFERENTE, "⚠️ Valor diferente"),
                                        (SO_EMPRESA, "🟦 Só na empresa"), (SO_FUNCIONARIOS, "🟥 Só nos funcionários"),
                                        (DUPLICADA, "🔁 Duplicadas")]):
    coluna.metric(rotulo, int(contagem.get(status, 0)))

total_emp = detalhe.drop_duplicates("OS")["Valor empresa"].sum()
total_func = detalhe["Valor funcionário"].sum()
def reais(v: float) -> str:
    # "\$" porque o Streamlit entende "$...$" como formula matematica
    return "R\\$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


st.write(f"**Total pago pela empresa:** {reais(total_emp)} · **Total declarado pelos funcionários:** {reais(total_func)} · "
         f"**Diferença:** {reais(total_func - total_emp)}")

detalhe = detalhe.astype(object).where(detalhe.notna(), "—")  # celula vazia aparece como "—", nao "None"
aba1, aba2, aba3 = st.tabs(["Divergências", "Por funcionário", "Todas as OS"])
with aba1:
    problemas = detalhe[detalhe["Status"] != OK]
    st.dataframe(problemas, hide_index=True, width="stretch") if len(problemas) else st.success("Tudo bate! 🎉")
with aba2:
    st.dataframe(resultado["Por funcionário"], hide_index=True, width="stretch")
with aba3:
    filtro = st.multiselect("Filtrar status", sorted(detalhe["Status"].unique()), placeholder="Todos")
    st.dataframe(detalhe[detalhe["Status"].isin(filtro)] if filtro else detalhe, hide_index=True, width="stretch")

# Excel com tudo, uma aba por tabela
saida = BytesIO()
with pd.ExcelWriter(saida, engine="openpyxl") as w:
    for nome, tabela in resultado.items():
        tabela.to_excel(w, sheet_name=nome, index=False)
st.download_button("⬇️ Baixar relatório (Excel)", saida.getvalue(), "conciliacao_os.xlsx", type="primary")
