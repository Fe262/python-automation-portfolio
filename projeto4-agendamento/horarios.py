"""
Regras de horario do estabelecimento.

Fica separado do resto do app porque e a parte mais importante e mais facil de errar:
assim da para testar sozinha (ver tests/test_app.py).
"""
from datetime import date, datetime, time, timedelta

ABERTURA = time(9, 0)
FECHAMENTO = time(18, 0)
INTERVALO_MIN = 30          # de quanto em quanto tempo oferecemos um horario (9:00, 9:30, 10:00...)
DIAS_FECHADOS = {6}         # 0 = segunda ... 6 = domingo


def horarios_livres(dia: date, duracao_min: int,
                    ocupados: list[tuple[datetime, datetime]],
                    agora: datetime) -> list[datetime]:
    """Lista os horarios de inicio possiveis para um servico naquele dia.

    Um horario so entra na lista se:
      - o estabelecimento abre nesse dia;
      - o servico termina ate o fechamento;
      - ainda nao passou;
      - nao bate com nenhum agendamento ja marcado.
    """
    if dia.weekday() in DIAS_FECHADOS:
        return []

    duracao = timedelta(minutes=duracao_min)
    atual = datetime.combine(dia, ABERTURA)
    fim_do_dia = datetime.combine(dia, FECHAMENTO)

    livres = []
    while atual + duracao <= fim_do_dia:
        fim = atual + duracao
        # Dois horarios "batem" quando um comeca antes do outro terminar
        conflita = any(atual < fim_ocupado and fim > inicio_ocupado
                       for inicio_ocupado, fim_ocupado in ocupados)
        if atual > agora and not conflita:
            livres.append(atual)
        atual += timedelta(minutes=INTERVALO_MIN)
    return livres
