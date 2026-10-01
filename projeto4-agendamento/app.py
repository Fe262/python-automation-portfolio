"""
Agenda Facil - app web de agendamento para saloes, barbearias e clinicas.

Paginas:
    /                 cliente escolhe servico, dia e horario e marca
    /confirmado/<cod> comprovante do agendamento (codigo aleatorio)
    /admin            painel do dono (precisa de senha): agenda do dia, concluir/cancelar
    /admin/servicos   cadastrar e ativar/desativar servicos

Como rodar (na pasta do projeto):
    1. Copie .env.example para .env e troque a senha e a chave.
    2. flask --app app init-db      (cria o banco com servicos de exemplo)
    3. flask --app app run          (abre em http://127.0.0.1:5000)
"""
import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

import db
from horarios import horarios_livres

PASTA = Path(__file__).parent


def criar_app(config: dict | None = None) -> Flask:
    """Monta o app. Os testes chamam com uma configuracao propria (banco temporario)."""
    load_dotenv(PASTA / ".env")
    app = Flask(__name__)
    app.config.update(
        DATABASE=str(PASTA / "agenda.db"),
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        ADMIN_SENHA=os.environ.get("ADMIN_SENHA", ""),
        NOME_NEGOCIO=os.environ.get("NOME_NEGOCIO", "Barbearia Exemplo"),
    )
    if config:
        app.config.update(config)

    app.teardown_appcontext(db.fechar)

    @app.cli.command("init-db")
    def init_db():
        """Cria as tabelas e os servicos de exemplo."""
        db.criar_tabelas()
        print("Banco criado:", app.config["DATABASE"])

    registrar_rotas(app)
    return app


# ---------- Seguranca ----------

def token_csrf() -> str:
    """Codigo secreto colocado em cada formulario. Impede que outro site
    envie formularios em nome do usuario logado (ataque chamado CSRF)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def conferir_csrf() -> None:
    esperado = session.get("csrf")
    # Sem codigo na sessao = formulario nao veio do nosso site (vazio == vazio nao vale!)
    if not esperado or not secrets.compare_digest(request.form.get("csrf", ""), esperado):
        abort(400, "Formulario expirado. Volte e tente de novo.")


def exige_login(funcao):
    """Coloque @exige_login em cima de uma pagina para so o dono acessar."""
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", proximo=request.path))
        return funcao(*args, **kwargs)
    return protegida


# ---------- Ajudantes ----------

def ler_data(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def validar_cliente(nome: str, telefone: str) -> list[str]:
    erros = []
    if len(nome) < 3:
        erros.append("Digite seu nome.")
    if len(re.sub(r"\D", "", telefone)) not in (10, 11):
        erros.append("Telefone deve ter DDD + número.")
    return erros


# ---------- Paginas ----------

def registrar_rotas(app: Flask) -> None:
    app.jinja_env.globals.update(csrf=token_csrf, reais=reais)

    @app.get("/")
    def inicio():
        servicos = db.listar_servicos()
        servico = db.buscar_servico(request.args.get("servico", type=int) or 0)
        dia = ler_data(request.args.get("dia"))
        hoje = date.today()

        horarios = []
        if servico and servico["ativo"] and dia and hoje <= dia <= hoje + timedelta(days=60):
            horarios = horarios_livres(dia, servico["duracao_min"],
                                       db.ocupados_no_dia(dia.isoformat()), datetime.now())
        return render_template("inicio.html", servicos=servicos, servico=servico, dia=dia,
                               horarios=horarios, hoje=hoje, limite=hoje + timedelta(days=60))

    @app.post("/agendar")
    def agendar():
        conferir_csrf()
        servico = db.buscar_servico(request.form.get("servico", type=int) or 0)
        try:
            inicio = datetime.strptime(request.form.get("inicio", ""), db.FORMATO)
        except ValueError:
            inicio = None
        if not servico or not servico["ativo"] or not inicio:
            abort(400, "Dados do agendamento inválidos.")

        nome = request.form.get("nome", "").strip()
        telefone = request.form.get("telefone", "").strip()
        voltar = url_for("inicio", servico=servico["id"], dia=inicio.date().isoformat())

        erros = validar_cliente(nome, telefone)
        # Confere de novo no servidor: nunca confie so no que veio da pagina
        livres = horarios_livres(inicio.date(), servico["duracao_min"],
                                 db.ocupados_no_dia(inicio.date().isoformat()), datetime.now())
        if inicio not in livres:
            erros.append("Esse horário não está mais disponível. Escolha outro.")
        if erros:
            for erro in erros:
                flash(erro, "erro")
            return redirect(voltar)

        fim = inicio + timedelta(minutes=servico["duracao_min"])
        codigo = db.criar_agendamento(servico["id"], nome, telefone, inicio, fim)
        if codigo is None:  # alguem marcou no mesmo segundo
            flash("Esse horário acabou de ser ocupado. Escolha outro.", "erro")
            return redirect(voltar)
        return redirect(url_for("confirmado", codigo=codigo))

    @app.get("/confirmado/<codigo>")
    def confirmado(codigo):
        ag = db.buscar_por_codigo(codigo) or abort(404)
        return render_template("confirmado.html", ag=ag, inicio=datetime.strptime(ag["inicio"], db.FORMATO))

    # ----- Area do dono -----

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            conferir_csrf()
            senha_certa = app.config["ADMIN_SENHA"]
            if senha_certa and secrets.compare_digest(request.form.get("senha", ""), senha_certa):
                session.clear()
                session["admin"] = True
                proximo = request.args.get("proximo", "")
                # So redireciona para paginas do proprio site
                return redirect(proximo if proximo.startswith("/admin") else url_for("painel"))
            flash("Senha incorreta.", "erro")
        return render_template("login.html")

    @app.post("/admin/sair")
    def sair():
        conferir_csrf()
        session.clear()
        return redirect(url_for("inicio"))

    @app.get("/admin")
    @exige_login
    def painel():
        dia = ler_data(request.args.get("dia")) or date.today()
        agenda = db.listar_agendamentos(dia.isoformat())
        ativos = [a for a in agenda if a["status"] != "cancelado"]
        return render_template("painel.html", dia=dia, agenda=agenda,
                               total=sum(a["preco"] for a in ativos), qtd=len(ativos),
                               anterior=dia - timedelta(days=1), seguinte=dia + timedelta(days=1))

    @app.post("/admin/agendamento/<int:agendamento_id>/status")
    @exige_login
    def status(agendamento_id):
        conferir_csrf()
        novo = request.form.get("status")
        if novo not in ("marcado", "concluido", "cancelado"):
            abort(400)
        ag = db.buscar_agendamento(agendamento_id) or abort(404)
        db.mudar_status(agendamento_id, novo)
        return redirect(url_for("painel", dia=ag["inicio"][:10]))

    @app.route("/admin/servicos", methods=["GET", "POST"])
    @exige_login
    def servicos():
        if request.method == "POST":
            conferir_csrf()
            nome = request.form.get("nome", "").strip()
            duracao = request.form.get("duracao", type=int)
            preco = request.form.get("preco", type=lambda v: float(v.replace(",", ".")))
            if len(nome) < 2 or not duracao or duracao % 30 or not 30 <= duracao <= 480 or preco is None or preco < 0:
                flash("Confira os dados: nome, duração em múltiplos de 30 min e preço.", "erro")
            else:
                db.criar_servico(nome, duracao, preco)
                flash(f"Serviço \"{nome}\" cadastrado.", "ok")
            return redirect(url_for("servicos"))
        return render_template("servicos.html", servicos=db.listar_servicos(somente_ativos=False))

    @app.post("/admin/servicos/<int:servico_id>/alternar")
    @exige_login
    def alternar(servico_id):
        conferir_csrf()
        db.alternar_servico(servico_id)
        return redirect(url_for("servicos"))


app = criar_app()
