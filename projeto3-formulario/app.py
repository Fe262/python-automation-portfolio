"""
Formulario de pedidos de orcamento -> planilha Excel.

O que faz:
    - Aba "Novo pedido": o cliente preenche um formulario (nome, contato, servico...).
      Os dados sao conferidos e salvos numa planilha Excel.
    - Aba "Painel": mostra todos os pedidos, com filtro e botao para baixar a planilha.

Como rodar:
    streamlit run app.py
Abre sozinho no navegador (endereco http://localhost:8501).

Os pedidos ficam em: dados/pedidos.xlsx (so no seu computador).
"""
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

ARQUIVO = Path(__file__).parent / "dados" / "pedidos.xlsx"
COLUNAS = ["Data", "Nome", "E-mail", "Telefone", "Servico", "Orcamento", "Descricao", "Status"]
SERVICOS = ["Site", "Automacao de planilha", "Leitura de PDF", "Integracao entre sistemas", "Outro"]
ORCAMENTOS = ["Ate R$ 500", "R$ 500 a R$ 1.500", "Acima de R$ 1.500", "Nao sei"]


# ---------- Ler e salvar a planilha ----------

def carregar_pedidos() -> pd.DataFrame:
    """Le a planilha. Se ainda nao existir, comeca uma vazia."""
    if ARQUIVO.exists():
        return pd.read_excel(ARQUIVO)
    return pd.DataFrame(columns=COLUNAS)


def salvar_pedido(pedido: dict) -> None:
    """Acrescenta uma linha na planilha."""
    ARQUIVO.parent.mkdir(exist_ok=True)
    pedidos = pd.concat([carregar_pedidos(), pd.DataFrame([pedido])], ignore_index=True)
    pedidos.to_excel(ARQUIVO, index=False)


# ---------- Conferir os dados digitados ----------

def validar(nome: str, email: str, telefone: str, descricao: str) -> list[str]:
    """Devolve a lista de erros. Lista vazia = tudo certo."""
    erros = []
    if len(nome.strip()) < 3:
        erros.append("Digite seu nome completo.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        erros.append("E-mail invalido.")
    if len(re.sub(r"\D", "", telefone)) not in (10, 11):  # so os numeros: DDD + telefone
        erros.append("Telefone deve ter DDD + numero (10 ou 11 digitos).")
    if len(descricao.strip()) < 10:
        erros.append("Descreva o que voce precisa (pelo menos 10 letras).")
    return erros


# ---------- Telas ----------

st.set_page_config(page_title="Pedido de orcamento", page_icon="📝")
st.title("📝 Pedido de orcamento")
aba_form, aba_painel = st.tabs(["Novo pedido", "Painel"])

def enviar():
    """Roda quando clicam em "Enviar pedido".
    Se tiver erro, mantem o que foi digitado. Se der certo, salva e limpa os campos."""
    s = st.session_state  # onde o Streamlit guarda o valor de cada campo
    s.erros = validar(s.nome, s.email, s.telefone, s.descricao)
    s.sucesso = not s.erros
    if s.sucesso:
        salvar_pedido({
            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Nome": s.nome.strip(), "E-mail": s.email.strip(), "Telefone": s.telefone.strip(),
            "Servico": s.servico, "Orcamento": s.orcamento,
            "Descricao": s.descricao.strip(), "Status": "Novo",
        })
        for campo in ("nome", "email", "telefone", "descricao"):
            s[campo] = ""


with aba_form:
    with st.form("pedido"):
        st.text_input("Nome completo", key="nome")
        st.text_input("E-mail", key="email")
        st.text_input("Telefone (com DDD)", placeholder="(11) 91234-5678", key="telefone")
        st.selectbox("Qual servico?", SERVICOS, key="servico")
        # O Streamlit entende "$...$" como formula matematica; o "\$" mostra o cifrao normal
        st.radio("Orcamento aproximado", ORCAMENTOS, horizontal=True, key="orcamento",
                 format_func=lambda opcao: opcao.replace("$", "\\$"))
        st.text_area("Descreva o que voce precisa", key="descricao")
        st.form_submit_button("Enviar pedido", on_click=enviar)

    for erro in st.session_state.get("erros", []):
        st.error(erro)
    if st.session_state.get("sucesso"):
        st.success("Pedido enviado! Responderemos em ate 24 horas.")
        st.session_state.sucesso = False  # mostra a mensagem so uma vez

with aba_painel:
    pedidos = carregar_pedidos()
    if pedidos.empty:
        st.info("Nenhum pedido ainda.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("Total de pedidos", len(pedidos))
        col2.metric("Novos (sem resposta)", int((pedidos["Status"] == "Novo").sum()))

        filtro = st.multiselect("Filtrar por servico", SERVICOS, placeholder="Todos os servicos")
        if filtro:
            pedidos = pedidos[pedidos["Servico"].isin(filtro)]
        st.dataframe(pedidos, use_container_width=True, hide_index=True)

        # Botao para baixar a planilha (ja filtrada)
        arquivo = BytesIO()
        pedidos.to_excel(arquivo, index=False)
        st.download_button("Baixar planilha (Excel)", arquivo.getvalue(), "pedidos.xlsx")
