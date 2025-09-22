from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
from financas_logic import GerenciadorFinancas
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from flask_bcrypt import Bcrypt


app = Flask(__name__)
# Chave secreta OBRIGATÓRIA para formulários e sessões
# Em um app real, NUNCA deixe essa chave visível. Use variáveis de ambiente.
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-dificil-de-adivinhar-12345'


# --- Forçar criação das tabelas ao iniciar o app e logar caminho do banco ---
import os
db_path = os.path.abspath('financas.db')
print(f'Banco de dados será criado/aberto em: {db_path}')
try:
    gerenciador = GerenciadorFinancas(db_file=db_path)
    gerenciador.connect()
    print('Tabelas do banco de dados garantidas/criadas com sucesso.')
    gerenciador.close()
except Exception as e:
    print(f'Erro ao criar tabelas do banco: {e}')

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
# Para onde o Flask-Login redireciona se o usuário tentar acessar uma página protegida sem login
login_manager.login_view = 'login' 
# Mensagem de "Faça login" (opcional)
login_manager.login_message_category = 'info' 


# --- Modelo de Usuário para o Flask-Login ---

# Esta classe UserMixin dá ao nosso 'User' os atributos do Flask-Login 
# (is_authenticated, is_active, is_anonymous, get_id())
class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email
        self.contas = [] # Novo: vamos guardar as contas do usuário aqui

@login_manager.user_loader
def load_user(user_id):
    """Callback do Flask-Login para recarregar o usuário E SUAS CONTAS."""
    gerenciador = None
    try:
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        user_data = gerenciador.buscar_usuario_por_id(int(user_id))
        if user_data:
            user = User(id=user_data[0], email=user_data[1])
            # Carrega as contas do usuário e anexa ao objeto 'user'
            user.contas = gerenciador.listar_contas_por_usuario(user.id)
            return user
        return None
    except Exception as e:
        print(f"Erro ao carregar usuário: {e}")
        return None
    finally:
        if gerenciador:
            gerenciador.close()

# --- Formulários com Flask-WTF ---

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    senha = PasswordField('Senha', validators=[DataRequired()])
    confirmar_senha = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('senha', message='As senhas não batem.')])
    submit = SubmitField('Cadastrar')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    senha = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

# --- Rotas da Aplicação ---


@app.route('/')
@login_required 
def index():
    gerenciador = None
    try:
        if not current_user.contas:
            flash('Bem-vindo! Por favor, crie sua primeira conta (ex: Carteira) para começar.', 'info')
            return redirect(url_for('contas'))
        
        hoje = datetime.now()
        mes_selecionado = request.args.get('mes', default=hoje.month, type=int)
        ano_selecionado = request.args.get('ano', default=hoje.year, type=int)

        lista_meses = [
            (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
            (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
            (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
        ]
        lista_anos = [hoje.year - 1, hoje.year, hoje.year + 1]

        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        
        user_id = current_user.id 
        
        receitas, despesas, saldo_periodo = gerenciador.calcular_resumo(user_id, mes_selecionado, ano_selecionado)
        
        # --- LÓGICA DE SALDO SEPARADO ---
        contas_com_saldo = gerenciador.listar_contas_com_saldo(user_id)
        contas_dinheiro = [c for c in contas_com_saldo if c['tipo_conta'] != 'cartao_de_credito']
        contas_cartao = [c for c in contas_com_saldo if c['tipo_conta'] == 'cartao_de_credito']
        saldo_total_dinheiro = sum(c['saldo_atual'] for c in contas_dinheiro)
        total_faturas = sum(abs(c['saldo_atual']) for c in contas_cartao) 
        
        transacoes_tuplas = gerenciador.ler_transacoes(user_id, mes_selecionado, ano_selecionado)
        trans_dicts = [dict(t) for t in transacoes_tuplas]
        
        return render_template('index.html', 
                               receitas=receitas,
                               despesas=despesas,
                               saldo_periodo=saldo_periodo,
                               contas_dinheiro=contas_dinheiro,
                               contas_cartao=contas_cartao,
                               saldo_total_dinheiro=saldo_total_dinheiro,
                               total_faturas=total_faturas,
                               transacoes=trans_dicts,
                               mes_selecionado=mes_selecionado,
                               ano_selecionado=ano_selecionado,
                               lista_meses=lista_meses,
                               lista_anos=lista_anos,
                               lista_contas_usuario=current_user.contas)
    except Exception as e:
        print(f"Erro no index: {e}")
        return "Ocorreu um erro ao carregar a página.", 500
    finally:
        if gerenciador:
            gerenciador.close()

@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    gerenciador = None
    try:
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        
        tipo = request.form['tipo']
        descricao = request.form['descricao']
        valor = float(request.form['valor'].replace(',', '.'))
        categoria = request.form['categoria']
        conta_id = request.form['conta_id'] # NOVO CAMPO
        user_id = current_user.id
        
        # Validação
        if not conta_id:
            flash('Erro: Conta não selecionada.', 'danger')
            return redirect(url_for('index'))
            
        gerenciador.adicionar_transacao(
            tipo=tipo, 
            descricao=descricao, 
            valor=valor, 
            categoria=categoria, 
            user_id=user_id, 
            conta_id=conta_id
        )
        flash('Transação adicionada com sucesso!', 'success')
        
    except Exception as e:
        print(f"Erro ao adicionar via web: {e}")
        flash('Erro ao adicionar transação.', 'danger')
    finally:
        if gerenciador:
            gerenciador.close()
            
    return redirect(url_for('index'))
    # --- Novos Métodos para CRUD ---

    def buscar_transacao_por_id(self, transacao_id, user_id):
        """Busca uma transação específica, garantindo que ela pertença ao usuário."""
        self.cursor.execute(
            "SELECT * FROM transacoes WHERE id = ? AND user_id = ?",
            (transacao_id, user_id)
        )
        # Retorna os dados como um dicionário para facilitar o uso no template
        data = self.cursor.fetchone()
        if not data:
            return None
            
        # Converte a tupla (id, data, tipo, ...) em um dicionário
        colunas = [desc[0] for desc in self.cursor.description]
        return dict(zip(colunas, data))


    def atualizar_transacao(self, transacao_id, tipo, descricao, valor, categoria, user_id):
        """Atualiza uma transação específica do usuário."""
        if tipo == 'despesa':
            valor = -abs(valor)
        
        try:
            self.cursor.execute('''
                UPDATE transacoes 
                SET tipo = ?, descricao = ?, valor = ?, categoria = ?
                WHERE id = ? AND user_id = ? 
            ''', (tipo, descricao, valor, categoria, transacao_id, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao atualizar transação: {e}")
            return False

    def excluir_transacao(self, transacao_id, user_id):
        """Exclui uma transação específica do usuário."""
        try:
            # A checagem 'AND user_id = ?' é crucial para segurança!
            self.cursor.execute(
                "DELETE FROM transacoes WHERE id = ? AND user_id = ?",
                (transacao_id, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao excluir transação: {e}")
            return False

# --- Novas Rotas de Autenticação ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Se o usuário já está logado, manda ele pro index
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = RegisterForm()
    if form.validate_on_submit(): # Verifica se o formulário foi enviado e é válido
        gerenciador = None
        try:
            gerenciador = GerenciadorFinancas()
            gerenciador.connect()
            
            email = form.email.data
            senha = form.senha.data
            
            sucesso = gerenciador.registrar_usuario(email, senha)
            
            if sucesso:
                flash('Conta criada com sucesso! Faça o login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Este email já está cadastrado. Tente outro.', 'danger')
                
        except Exception as e:
            print(f"Erro no registro: {e}")
            flash('Ocorreu um erro durante o cadastro.', 'danger')
        finally:
            if gerenciador:
                gerenciador.close()
                
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        gerenciador = None
        try:
            gerenciador = GerenciadorFinancas()
            gerenciador.connect()
            
            email = form.email.data
            senha = form.senha.data
            
            user_id = gerenciador.verificar_usuario(email, senha)
            
            if user_id:
                # Login bem-sucedido!
                user_obj = User(id=user_id, email=email)
                login_user(user_obj) # Função do Flask-Login que cria a sessão
                
                # Redireciona para a página que o usuário tentou acessar (ou 'index')
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            else:
                flash('Email ou senha incorretos. Tente novamente.', 'danger')
                
        except Exception as e:
            print(f"Erro no login: {e}")
            flash('Ocorreu um erro durante o login.', 'danger')
        finally:
            if gerenciador:
                gerenciador.close()

    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user() # Função do Flask-Login que limpa a sessão
    flash('Logout feito com sucesso.', 'info')
    return redirect(url_for('login'))


# --- Novas Rotas de CRUD ---

@app.route('/excluir/<int:transacao_id>', methods=['POST'])
@login_required
def excluir_transacao(transacao_id):
    gerenciador = None
    try:
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        sucesso = gerenciador.excluir_transacao(transacao_id, current_user.id)
        if sucesso:
            flash('Transação excluída com sucesso.', 'success')
        else:
            flash('Erro ao excluir transação.', 'danger')
    except Exception as e:
        print(f"Erro ao excluir: {e}")
        flash('Ocorreu um erro ao excluir.', 'danger')
    finally:
        if gerenciador:
            gerenciador.close()
    return redirect(url_for('index'))

@app.route('/editar/<int:transacao_id>', methods=['GET', 'POST'])
@login_required
def editar_transacao(transacao_id):
    gerenciador = None
    try:
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        
        transacao = gerenciador.buscar_transacao_por_id(transacao_id, current_user.id)
        
        if not transacao:
            flash('Transação não encontrada ou não pertence a você.', 'danger')
            return redirect(url_for('index'))

        if request.method == 'POST':
            tipo = request.form['tipo']
            descricao = request.form['descricao']
            valor = float(request.form['valor'].replace(',', '.'))
            categoria = request.form['categoria']
            conta_id = request.form['conta_id'] # NOVO CAMPO
            
            sucesso = gerenciador.atualizar_transacao(
                transacao_id, tipo, descricao, valor, categoria, current_user.id, conta_id
            )
            
            if sucesso:
                flash('Transação atualizada com sucesso!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Erro ao atualizar transação.', 'danger')

        # GET: Mostra o formulário
        # Passa a lista de contas do usuário para o dropdown
        return render_template('editar.html', 
                               transacao=transacao, 
                               lista_contas_usuario=current_user.contas)
    except Exception as e:
        print(f"Erro ao editar: {e}")
        flash('Ocorreu um erro ao editar.', 'danger')
        return redirect(url_for('index'))
    finally:
        if gerenciador:
            gerenciador.close()

# --- Rota da API para o Gráfico ---

@app.route('/api/dados_grafico')
@login_required
def api_dados_grafico():
    gerenciador = None
    try:
        hoje = datetime.now()
        mes = request.args.get('mes', default=hoje.month, type=int)
        ano = request.args.get('ano', default=hoje.year, type=int)
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        dados_brutos = gerenciador.relatorio_por_categoria(current_user.id, mes, ano)
        labels = []
        data = []
        for item in dados_brutos:
            labels.append(item[0])
            data.append(abs(item[1]))
        return jsonify(labels=labels, data=data)
    except Exception as e:
        print(f"Erro na API de dados: {e}")
        return jsonify({'erro': 'Erro ao buscar dados'}), 500
    finally:
        if gerenciador:
            gerenciador.close()


# --- NOVAS Rotas para Gestão de Contas ---

@app.route('/contas', methods=['GET', 'POST'])
@login_required
def contas():
    gerenciador = None
    if request.method == 'POST':
        # --- Lógica para ADICIONAR uma nova conta ---
        nome = request.form['nome']
        saldo_inicial_str = request.form['saldo_inicial'].replace(',', '.') or '0'
        tipo_conta = request.form['tipo_conta']
        
        if not nome or not tipo_conta:
            flash('Nome e Tipo da Conta são obrigatórios.', 'danger')
        else:
            try:
                saldo_inicial = float(saldo_inicial_str)
                limite = None
                data_fechamento = None
                data_vencimento = None
                
                # Se for cartão, pega os dados extras
                if tipo_conta == 'cartao_de_credito':
                    saldo_inicial = 0 
                    limite_str = request.form['limite'].replace(',', '.') or None
                    if limite_str:
                        limite = float(limite_str)
                    data_fechamento = request.form['data_fechamento'] or None
                    data_vencimento = request.form['data_vencimento'] or None
                
                gerenciador = GerenciadorFinancas()
                gerenciador.connect()
                gerenciador.criar_conta(
                    current_user.id, nome, saldo_inicial, tipo_conta, 
                    limite, data_fechamento, data_vencimento
                )
                
                flash('Conta criada com sucesso!', 'success')
                load_user(current_user.id)
                return redirect(url_for('index'))
                
            except Exception as e:
                print(e)
                flash(f'Erro ao criar conta: {e}', 'danger')
            finally:
                if gerenciador:
                    gerenciador.close()
    
    # --- Lógica GET (mostrar contas) ---
    contas_com_saldo = []
    try:
        gerenciador = GerenciadorFinancas()
        gerenciador.connect()
        contas_com_saldo = gerenciador.listar_contas_com_saldo(current_user.id)
    except Exception as e:
        print(e)
        flash('Erro ao carregar contas.', 'danger')
    finally:
        if gerenciador:
            gerenciador.close()
            
    return render_template('contas.html', contas=contas_com_saldo)

# (No futuro, podemos adicionar /contas/editar e /contas/excluir, mas por agora, criar é o suficiente)

# --- Ponto de entrada ---
if __name__ == '__main__':
    app.run(debug=True)