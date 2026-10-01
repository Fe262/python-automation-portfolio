"""
Cria duas planilhas FALSAS para testar a conciliacao, com divergencias de proposito:
  - 3 OS com valor diferente
  - 2 OS que a empresa pagou e ninguem registrou
  - 2 OS registradas por funcionario que a empresa nao pagou
  - 1 OS registrada por dois funcionarios
  - formatos baguncados (OS-00123, "R$ 1.234,50") como no mundo real

Como rodar:  python gerar_exemplo.py
"""
import random
from pathlib import Path

import pandas as pd

random.seed(3)
PASTA = Path(__file__).parent / "exemplo"
PASTA.mkdir(exist_ok=True)
TECNICOS = ["Carlos", "Juliana", "Marcos", "Patrícia"]

ordens = [{"os": 5000 + i, "tecnico": random.choice(TECNICOS),
           "valor": random.choice([85, 120, 150, 180, 220, 260, 310])} for i in range(60)]

empresa = [{"Número OS": o["os"], "Data conclusão": f"2026-09-{random.randint(1, 30):02d}",
            "Valor pago": o["valor"]} for o in ordens]
funcionarios = [{"Técnico": o["tecnico"], "Ordem de serviço": f"OS-{o['os']:05d}",
                 "Valor": f"R$ {o['valor']:.2f}".replace(".", ",")} for o in ordens]

for i in (3, 17, 41):                                   # valor diferente
    funcionarios[i]["Valor"] = f"R$ {ordens[i]['valor'] + 40:.2f}".replace(".", ",")
del funcionarios[50]; del funcionarios[25]              # empresa pagou, ninguem registrou (OS 5025 e 5050)
funcionarios += [{"Técnico": "Marcos", "Ordem de serviço": "OS-05099", "Valor": "R$ 150,00"},
                 {"Técnico": "Juliana", "Ordem de serviço": "os 5098", "Valor": "R$ 220,00"}]  # empresa nao pagou
funcionarios.append({"Técnico": "Patrícia", "Ordem de serviço": f"OS-{ordens[10]['os']:05d}",
                     "Valor": f"R$ {ordens[10]['valor']:.2f}".replace(".", ",")})            # duplicada

random.shuffle(funcionarios)
pd.DataFrame(empresa).to_excel(PASTA / "empresa_setembro.xlsx", index=False)
pd.DataFrame(funcionarios).to_excel(PASTA / "funcionarios_setembro.xlsx", index=False)
print(f"Planilhas criadas em {PASTA.name}/: {len(empresa)} OS da empresa, {len(funcionarios)} linhas dos funcionários")
