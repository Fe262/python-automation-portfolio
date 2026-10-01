"""
Conciliacao de planilhas: compara a planilha da EMPRESA (o que foi pago/aprovado)
com a planilha dos FUNCIONARIOS (o que cada um diz que fez).

Para cada ordem de servico (OS) diz se esta:
    OK                       -> esta nas duas, com o mesmo valor
    Valor diferente          -> esta nas duas, mas os valores nao batem
    So na empresa            -> a empresa pagou, mas nenhum funcionario registrou
    So nos funcionarios      -> funcionario registrou, mas a empresa nao pagou
    Duplicada                -> a mesma OS aparece mais de uma vez (ex: dois funcionarios)

Fica separado da tela (app.py) para poder ser testado sozinho (tests/).
"""
import re

import pandas as pd

OK = "OK"
VALOR_DIFERENTE = "Valor diferente"
SO_EMPRESA = "Só na empresa (ninguém registrou)"
SO_FUNCIONARIOS = "Só nos funcionários (empresa não pagou)"
DUPLICADA = "Duplicada"


def normalizar_os(valor) -> str:
    """'  os-00123 ' e 'OS 123' viram '123'; '123.0' (numero que o Excel salvou) vira '123'."""
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().upper()
    texto = re.sub(r"\.0$", "", texto)                 # 123.0 -> 123
    texto = re.sub(r"^(OS|O\.S\.|ORDEM)\s*[-:#]?\s*", "", texto)
    texto = re.sub(r"[\s\-./]", "", texto)
    return texto.lstrip("0") or texto


def para_numero(valor) -> float | None:
    """Aceita 1234.5, '1.234,50', 'R$ 1.234,50'. Devolve None se nao der."""
    if pd.isna(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^\d,.\-]", "", str(valor))
    if "," in texto:                                    # formato brasileiro
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def conciliar(empresa: pd.DataFrame, funcionarios: pd.DataFrame,
              os_emp: str, valor_emp: str,
              os_func: str, valor_func: str, nome_func: str,
              tolerancia: float = 0.01) -> dict[str, pd.DataFrame]:
    """Recebe as duas planilhas e o nome das colunas de cada uma. Devolve as tabelas do resultado."""
    e = pd.DataFrame({"OS": empresa[os_emp].map(normalizar_os),
                      "OS original": empresa[os_emp].astype(str),
                      "Valor empresa": empresa[valor_emp].map(para_numero)})
    f = pd.DataFrame({"OS": funcionarios[os_func].map(normalizar_os),
                      "Funcionário": funcionarios[nome_func].astype(str).str.strip(),
                      "Valor funcionário": funcionarios[valor_func].map(para_numero)})
    e = e[e["OS"] != ""]
    f = f[f["OS"] != ""]

    # Quantas vezes cada OS aparece em cada planilha
    e["Vezes na empresa"] = e.groupby("OS")["OS"].transform("size")
    f["Vezes nos funcionários"] = f.groupby("OS")["OS"].transform("size")

    # Junta as duas pela OS (outer = mantem quem esta so de um lado)
    juntas = e.drop_duplicates("OS").merge(f, on="OS", how="outer")
    juntas["Vezes na empresa"] = juntas["Vezes na empresa"].fillna(0).astype(int)
    juntas["Vezes nos funcionários"] = juntas["Vezes nos funcionários"].fillna(0).astype(int)
    juntas["Diferença"] = (juntas["Valor funcionário"] - juntas["Valor empresa"]).round(2)

    def status(l):
        if l["Vezes na empresa"] > 1 or l["Vezes nos funcionários"] > 1:
            return DUPLICADA
        if l["Vezes na empresa"] == 0:
            return SO_FUNCIONARIOS
        if l["Vezes nos funcionários"] == 0:
            return SO_EMPRESA
        if pd.isna(l["Diferença"]) or abs(l["Diferença"]) > tolerancia:
            return VALOR_DIFERENTE
        return OK

    juntas["Status"] = juntas.apply(status, axis=1)
    detalhe = juntas[["OS", "Funcionário", "Valor empresa", "Valor funcionário", "Diferença",
                      "Vezes na empresa", "Vezes nos funcionários", "Status"]].sort_values(["Status", "OS"])

    # Resumo por funcionario: o que declarou x o que a empresa confirmou
    confirmadas = detalhe[detalhe["Status"].isin([OK, VALOR_DIFERENTE])]
    por_func = detalhe[detalhe["Funcionário"].notna()].groupby("Funcionário").agg(
        **{"OS declaradas": ("OS", "size"), "Valor declarado": ("Valor funcionário", "sum")})
    conf = confirmadas.groupby("Funcionário").agg(**{"OS confirmadas": ("OS", "size"),
                                                     "Valor confirmado (empresa)": ("Valor empresa", "sum")})
    por_func = por_func.join(conf, how="left").fillna(0)
    por_func["OS confirmadas"] = por_func["OS confirmadas"].astype(int)
    por_func["Diferença"] = (por_func["Valor declarado"] - por_func["Valor confirmado (empresa)"]).round(2)

    resumo = detalhe.groupby("Status").agg(**{"Quantidade": ("OS", "size"),
                                              "Valor empresa": ("Valor empresa", "sum"),
                                              "Valor funcionários": ("Valor funcionário", "sum")}).reset_index()
    return {"Resumo": resumo, "Por funcionário": por_func.reset_index(), "Detalhe": detalhe}


def adivinhar_coluna(colunas: list[str], palavras: list[str]) -> int:
    """Sugere qual coluna usar (ex: a que tem 'OS' ou 'ordem' no nome). Devolve a posicao."""
    for i, c in enumerate(colunas):
        if any(p in str(c).lower() for p in palavras):
            return i
    return 0
