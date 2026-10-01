"""
Testes automaticos. Rodar na pasta do projeto:
    python -m pytest -v

Cada teste usa um banco temporario novo, entao nao mexe na agenda de verdade.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))  # para achar app.py, db.py...

import db  # noqa: E402
from app import criar_app  # noqa: E402
from horarios import horarios_livres  # noqa: E402

SENHA = "senha-de-teste"


def proxima_segunda() -> date:
    """Uma segunda-feira no futuro (dia em que o estabelecimento abre)."""
    hoje = date.today()
    return hoje + timedelta(days=7 - hoje.weekday())


@pytest.fixture
def app(tmp_path):
    app = criar_app({"TESTING": True, "DATABASE": str(tmp_path / "teste.db"),
                     "ADMIN_SENHA": SENHA, "SECRET_KEY": "teste"})
    with app.app_context():
        db.criar_tabelas()
    return app


@pytest.fixture
def cliente(app):
    return app.test_client()


def pegar_csrf(cliente) -> str:
    cliente.get("/admin/login")  # visitar uma pagina com formulario cria o codigo na sessao
    with cliente.session_transaction() as sessao:
        return sessao["csrf"]


def agendar(cliente, inicio: str, servico=1, nome="Cliente Teste", telefone="(11) 91234-5678"):
    return cliente.post("/agendar", data={"csrf": pegar_csrf(cliente), "servico": servico,
                                          "inicio": inicio, "nome": nome, "telefone": telefone})


def entrar(cliente, senha=SENHA):
    return cliente.post("/admin/login", data={"csrf": pegar_csrf(cliente), "senha": senha})


# ---------- Regras de horario ----------

def test_domingo_fechado():
    domingo = proxima_segunda() - timedelta(days=1)
    assert horarios_livres(domingo, 30, [], datetime(2000, 1, 1)) == []


def test_dia_livre_tem_horarios_das_9_ate_17_30():
    livres = horarios_livres(proxima_segunda(), 30, [], datetime(2000, 1, 1))
    assert livres[0].strftime("%H:%M") == "09:00"
    assert livres[-1].strftime("%H:%M") == "17:30"  # 30 min terminando as 18h
    assert len(livres) == 18


def test_servico_longo_nao_passa_do_fechamento():
    livres = horarios_livres(proxima_segunda(), 90, [], datetime(2000, 1, 1))
    assert livres[-1].strftime("%H:%M") == "16:30"


def test_horario_ocupado_e_vizinhos_que_batem_somem():
    dia = proxima_segunda()
    ocupado = (datetime.combine(dia, datetime.min.time()).replace(hour=10),
               datetime.combine(dia, datetime.min.time()).replace(hour=11))
    livres = [h.strftime("%H:%M") for h in horarios_livres(dia, 60, [ocupado], datetime(2000, 1, 1))]
    assert "09:00" in livres and "11:00" in livres
    assert "09:30" not in livres and "10:00" not in livres and "10:30" not in livres


def test_horario_que_ja_passou_some():
    dia = proxima_segunda()
    agora = datetime.combine(dia, datetime.min.time()).replace(hour=12)
    livres = horarios_livres(dia, 30, [], agora)
    assert livres[0].strftime("%H:%M") == "12:30"


# ---------- Agendamento pelo site ----------

def test_agendar_e_horario_sai_da_lista(cliente):
    dia = proxima_segunda().isoformat()
    resposta = agendar(cliente, f"{dia}T10:00")
    assert resposta.status_code == 302 and "/confirmado/" in resposta.location

    confirmacao = cliente.get(resposta.location).get_data(as_text=True)
    assert "Agendado" in confirmacao and "10:00" in confirmacao

    pagina = cliente.get(f"/?servico=1&dia={dia}").get_data(as_text=True)
    assert f'value="{dia}T10:00"' not in pagina
    assert f'value="{dia}T10:30"' in pagina


def test_comprovante_nao_pode_ser_adivinhado(cliente):
    dia = proxima_segunda().isoformat()
    codigo = agendar(cliente, f"{dia}T10:00").location.rsplit("/", 1)[-1]
    assert len(codigo) >= 12
    assert cliente.get("/confirmado/1").status_code == 404


def test_nao_deixa_marcar_horario_ocupado(cliente, app):
    dia = proxima_segunda().isoformat()
    agendar(cliente, f"{dia}T10:00")
    resposta = agendar(cliente, f"{dia}T10:00", nome="Outra Pessoa")
    assert "/confirmado/" not in resposta.location
    with app.app_context():
        assert len(db.listar_agendamentos(dia)) == 1


def test_dados_invalidos_nao_agendam(cliente, app):
    dia = proxima_segunda().isoformat()
    resposta = agendar(cliente, f"{dia}T10:00", nome="A", telefone="123")
    assert "/confirmado/" not in resposta.location
    pagina = cliente.get(resposta.location).get_data(as_text=True)
    assert "Digite seu nome" in pagina and "DDD" in pagina


def test_sem_csrf_e_recusado(cliente):
    dia = proxima_segunda().isoformat()
    resposta = cliente.post("/agendar", data={"servico": 1, "inicio": f"{dia}T10:00",
                                              "nome": "Cliente", "telefone": "11912345678"})
    assert resposta.status_code == 400


# ---------- Area do dono ----------

def test_painel_exige_login(cliente):
    assert "/admin/login" in cliente.get("/admin").location


def test_senha_errada_nao_entra(cliente):
    entrar(cliente, senha="errada")
    assert cliente.get("/admin").status_code == 302


def test_sem_senha_configurada_ninguem_entra(app):
    app.config["ADMIN_SENHA"] = ""
    cliente = app.test_client()
    entrar(cliente, senha="")
    assert cliente.get("/admin").status_code == 302


def test_cancelar_libera_horario(cliente, app):
    dia = proxima_segunda().isoformat()
    agendar(cliente, f"{dia}T10:00")
    entrar(cliente)
    painel = cliente.get(f"/admin?dia={dia}").get_data(as_text=True)
    assert "Cliente Teste" in painel

    cliente.post("/admin/agendamento/1/status", data={"csrf": pegar_csrf(cliente), "status": "cancelado"})
    pagina = cliente.get(f"/?servico=1&dia={dia}").get_data(as_text=True)
    assert f'value="{dia}T10:00"' in pagina


def test_cadastrar_e_desativar_servico(cliente, app):
    entrar(cliente)
    csrf = pegar_csrf(cliente)
    pagina = cliente.post("/admin/servicos", follow_redirects=True,
                          data={"csrf": csrf, "nome": "Hidratacao", "duracao": 60, "preco": "80,50"})
    assert "cadastrado" in pagina.get_data(as_text=True)
    with app.app_context():
        novo = [s for s in db.listar_servicos() if s["nome"] == "Hidratacao"][0]
        assert novo["preco"] == 80.5

    cliente.post(f"/admin/servicos/{novo['id']}/alternar", data={"csrf": csrf})
    assert "Hidratacao" not in cliente.get("/").get_data(as_text=True)
