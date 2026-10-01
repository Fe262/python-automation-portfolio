"""
Cria uma planilha de vendas FALSA (dados inventados) para testar o relatorio.

Por que isso existe: no portfolio nao podemos usar dados reais de ninguem.
Entao geramos dados de exemplo parecidos com os de uma loja pequena.

Como rodar:
    python gerar_dados_exemplo.py
Resultado: cria o arquivo "vendas_exemplo.xlsx" nesta pasta.
"""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Sempre o mesmo "sorteio": assim a planilha sai igual toda vez que rodar
random.seed(42)

# Produtos da loja: nome -> (categoria, preco unitario)
PRODUTOS = {
    "Camiseta Basica": ("Roupas", 49.90),
    "Calca Jeans": ("Roupas", 139.90),
    "Tenis Casual": ("Calcados", 229.90),
    "Chinelo": ("Calcados", 39.90),
    "Bone": ("Acessorios", 59.90),
    "Mochila": ("Acessorios", 179.90),
}
VENDEDORES = ["Ana", "Bruno", "Carla", "Diego"]

inicio = date(2026, 1, 1)
linhas = []
for _ in range(600):  # 600 vendas espalhadas por 9 meses
    produto = random.choice(list(PRODUTOS))
    categoria, preco = PRODUTOS[produto]
    linhas.append({
        "Data": inicio + timedelta(days=random.randint(0, 272)),
        "Vendedor": random.choice(VENDEDORES),
        "Produto": produto,
        "Categoria": categoria,
        "Quantidade": random.randint(1, 4),
        "Preco Unitario": preco,
    })

tabela = pd.DataFrame(linhas).sort_values("Data")
arquivo = Path(__file__).parent / "vendas_exemplo.xlsx"
tabela.to_excel(arquivo, index=False)
print(f"Planilha criada: {arquivo.name} ({len(tabela)} vendas)")
