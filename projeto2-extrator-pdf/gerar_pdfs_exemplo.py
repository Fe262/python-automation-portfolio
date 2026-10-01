"""
Cria notas de servico FALSAS em PDF (dados inventados) para testar o extrator.

Como rodar:
    python gerar_pdfs_exemplo.py
Resultado: pasta "pdfs_exemplo" com 12 PDFs.
"""
import random
from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF

random.seed(7)  # mesmo sorteio toda vez

EMPRESAS = [
    ("Padaria Pao Quente Ltda", "12.345.678/0001-90"),
    ("Oficina Mecanica Roda Viva ME", "23.456.789/0001-01"),
    ("Clinica Sorriso Feliz Ltda", "34.567.890/0001-12"),
    ("Mercadinho Bom Preco EIRELI", "45.678.901/0001-23"),
    ("Studio Fit Academia Ltda", "56.789.012/0001-34"),
]
SERVICOS = [
    ("Manutencao de computadores", 180.00),
    ("Instalacao de rede Wi-Fi", 350.00),
    ("Suporte tecnico mensal", 450.00),
    ("Configuracao de impressora", 90.00),
    ("Backup e recuperacao de dados", 270.00),
]

pasta = Path(__file__).parent / "pdfs_exemplo"
pasta.mkdir(exist_ok=True)


def reais(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


for numero in range(1001, 1013):
    cliente, cnpj = random.choice(EMPRESAS)
    emissao = date(2026, 1, 5) + timedelta(days=random.randint(0, 260))
    itens = random.sample(SERVICOS, random.randint(1, 3))
    total = sum(preco for _, preco in itens)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "NOTA DE SERVICO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, "Prestador: TecFacil Informatica - CNPJ 98.765.432/0001-10", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 8, f"Nota No: {numero}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Data de emissao: {emissao:%d/%m/%Y}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Cliente: {cliente}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"CNPJ do cliente: {cnpj}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Servicos:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for nome, preco in itens:
        pdf.cell(0, 7, f"- {nome} ........ {reais(preco)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"VALOR TOTAL: {reais(total)}", new_x="LMARGIN", new_y="NEXT")
    pdf.output(pasta / f"nota_{numero}.pdf")

print(f"12 PDFs criados em: {pasta.name}/")
