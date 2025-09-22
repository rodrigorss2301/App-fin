import sqlite3
import bcrypt
from datetime import date

class GerenciadorFinancas:
    def __init__(self, db_file='financas.db'):
        self.db_file = db_file
        self.conn = None
        self.cursor = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)
        self.conn.row_factory = sqlite3.Row # Permite aceder aos dados por nome da coluna
        self.cursor = self.conn.cursor()
        self._criar_tabelas()

    def close(self):
        if self.conn:
            self.conn.close()

    def _criar_tabelas(self):
        """Cria as tabelas usuarios, contas e transacoes."""
        try:
            # Ativar suporte a foreign keys
            self.cursor.execute("PRAGMA foreign_keys = ON;")
            
            print("Iniciando criação de tabelas...")
            
            # Tabela de Usuários
            print("Criando tabela usuarios...")
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    senha_hash TEXT NOT NULL
                )
            ''')
            self.conn.commit()
            
            # Verificar se a tabela usuarios foi criada
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'")
            if self.cursor.fetchone():
                print("Tabela usuarios criada com sucesso")
            
            # NOVA Tabela de Contas
            print("Criando tabela contas...")
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS contas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    saldo_inicial REAL NOT NULL DEFAULT 0,
                    tipo_conta TEXT,
                    FOREIGN KEY (user_id) REFERENCES usuarios (id)
                )
            ''')
            self.conn.commit()
            
            # Verificar se a tabela contas foi criada
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contas'")
            if self.cursor.fetchone():
                print("Tabela contas criada com sucesso")
            
            # Tabela de Transações
            print("Criando tabela transacoes...")
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS transacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    descricao TEXT NOT NULL,
                    valor REAL NOT NULL,
                    categoria TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    conta_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES usuarios (id),
                    FOREIGN KEY (conta_id) REFERENCES contas (id)
                )
            ''')
            self.conn.commit()
            
            # Verificar se a tabela transacoes foi criada
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transacoes'")
            if self.cursor.fetchone():
                print("Tabela transacoes criada com sucesso")

            # Listar todas as tabelas para verificação final
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = self.cursor.fetchall()
            print(f"Tabelas existentes no banco: {[table[0] for table in tables]}")
            
        except Exception as e:
            print(f"ERRO ao criar tabelas: {e}")
            raise e

    # --- Métodos de Usuários (sem alteração) ---

    def registrar_usuario(self, email, senha_plana):
        try:
            senha_hash = bcrypt.hashpw(senha_plana.encode('utf-8'), bcrypt.gensalt())
            self.cursor.execute(
                "INSERT INTO usuarios (email, senha_hash) VALUES (?, ?)",
                (email, senha_hash)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False 

    def verificar_usuario(self, email, senha_plana):
        self.cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = ?", (email,))
        user_data = self.cursor.fetchone()
        if user_data:
            user_id, senha_hash = user_data
            if bcrypt.checkpw(senha_plana.encode('utf-8'), senha_hash):
                return user_id
        return None

    def buscar_usuario_por_id(self, user_id):
        self.cursor.execute("SELECT id, email FROM usuarios WHERE id = ?", (user_id,))
        return self.cursor.fetchone()

    # --- NOVOS Métodos para Contas ---

    def criar_conta(self, user_id, nome, saldo_inicial, tipo_conta, limite=None, data_fechamento=None, data_vencimento=None):
        try:
            self.cursor.execute(
                """
                INSERT INTO contas 
                (user_id, nome, saldo_inicial, tipo_conta, limite, data_fechamento, data_vencimento) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, nome, saldo_inicial, tipo_conta, limite, data_fechamento, data_vencimento)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao criar conta: {e}")
            return False
    
    def listar_contas_por_usuario(self, user_id):
        """Lista todas as contas de um usuário."""
        self.cursor.execute("SELECT * FROM contas WHERE user_id = ?", (user_id,))
        return self.cursor.fetchall()

    def listar_contas_com_saldo(self, user_id):
        """Lista todas as contas e calcula o saldo atual de cada uma."""
        contas = self.listar_contas_por_usuario(user_id)
        contas_com_saldo = []
        
        for conta in contas:
            # Pega o saldo das transações dessa conta
            self.cursor.execute(
                "SELECT SUM(valor) FROM transacoes WHERE user_id = ? AND conta_id = ?",
                (user_id, conta['id'])
            )
            soma_transacoes = self.cursor.fetchone()[0] or 0.0
            
            # O saldo atual é o inicial + transações
            saldo_atual = conta['saldo_inicial'] + soma_transacoes
            
            contas_com_saldo.append({
                'id': conta['id'],
                'nome': conta['nome'],
                'saldo_atual': saldo_atual
            })
        return contas_com_saldo

    def calcular_saldo_total(self, user_id):
        """Calcula o saldo total somando todas as contas."""
        # Pega a soma de todos os saldos iniciais
        self.cursor.execute("SELECT SUM(saldo_inicial) FROM contas WHERE user_id = ?", (user_id,))
        total_saldo_inicial = self.cursor.fetchone()[0] or 0.0
        
        # Pega a soma de todas as transações
        self.cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id = ?", (user_id,))
        total_transacoes = self.cursor.fetchone()[0] or 0.0
        
        return total_saldo_inicial + total_transacoes

    # --- Métodos de Transação (MODIFICADOS) ---

    def adicionar_transacao(self, tipo, descricao, valor, categoria, user_id, conta_id):
        """Adiciona transação (agora com conta_id)"""
        data = date.today().strftime('%Y-%m-%d')
        
        # Valor continua negativo para despesa, positivo para receita
        valor_real = -abs(valor) if tipo == 'despesa' else abs(valor)
        
        try:
            self.cursor.execute('''
                INSERT INTO transacoes (data, tipo, descricao, valor, categoria, user_id, conta_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (data, tipo, descricao, valor_real, categoria, user_id, conta_id))
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar transação: {e}")

    def ler_transacoes(self, user_id, mes=None, ano=None):
        """Lê transações, agora juntando o nome da conta (JOIN)"""
        query = '''
            SELECT t.*, c.nome as conta_nome 
            FROM transacoes t
            JOIN contas c ON t.conta_id = c.id
            WHERE t.user_id = ?
        '''
        params = [user_id]
        
        if mes:
            query += " AND strftime('%m', t.data) = ?"
            params.append(f"{mes:02d}")
        if ano:
            query += " AND strftime('%Y', t.data) = ?"
            params.append(str(ano))
            
        query += " ORDER BY t.data DESC"
        
        self.cursor.execute(query, tuple(params))
        return self.cursor.fetchall()

    def buscar_transacao_por_id(self, transacao_id, user_id):
        """Busca uma transação específica (agora retorna um dict)"""
        self.cursor.execute(
            "SELECT * FROM transacoes WHERE id = ? AND user_id = ?",
            (transacao_id, user_id)
        )
        data = self.cursor.fetchone()
        return data # Já será um dict por causa do conn.row_factory

    def atualizar_transacao(self, transacao_id, tipo, descricao, valor, categoria, user_id, conta_id):
        """Atualiza uma transação (agora inclui conta_id)"""
        valor_real = -abs(valor) if tipo == 'despesa' else abs(valor)
        
        try:
            self.cursor.execute('''
                UPDATE transacoes 
                SET tipo = ?, descricao = ?, valor = ?, categoria = ?, conta_id = ?
                WHERE id = ? AND user_id = ? 
            ''', (tipo, descricao, valor_real, categoria, conta_id, transacao_id, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao atualizar transação: {e}")
            return False

    def excluir_transacao(self, transacao_id, user_id):
        """Exclui uma transação (lógica não muda)"""
        try:
            self.cursor.execute(
                "DELETE FROM transacoes WHERE id = ? AND user_id = ?",
                (transacao_id, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao excluir transação: {e}")
            return False

    # --- Métodos de Resumo (lógica não muda, filtros já funcionam) ---

    def calcular_resumo(self, user_id, mes=None, ano=None):
        """Calcula as RECEITAS e DESPESAS do período (esta lógica está correta)"""
        # ... (este método pode ficar EXATAMENTE como estava na Etapa 3) ...
        query_receitas = "SELECT SUM(valor) FROM transacoes WHERE tipo = 'receita' AND user_id = ?"
        query_despesas = "SELECT SUM(valor) FROM transacoes WHERE tipo = 'despesa' AND user_id = ?"
        params_receitas = [user_id]
        params_despesas = [user_id]
        
        if mes:
            mes_str = f"{mes:02d}"
            query_receitas += " AND strftime('%m', data) = ?"
            query_despesas += " AND strftime('%m', data) = ?"
            params_receitas.append(mes_str)
            params_despesas.append(mes_str)
            
        if ano:
            ano_str = str(ano)
            query_receitas += " AND strftime('%Y', data) = ?"
            query_despesas += " AND strftime('%Y', data) = ?"
            params_receitas.append(ano_str)
            params_despesas.append(ano_str)
            
        self.cursor.execute(query_receitas, tuple(params_receitas))
        total_receitas = self.cursor.fetchone()[0] or 0.0
        
        self.cursor.execute(query_despesas, tuple(params_despesas))
        total_despesas = self.cursor.fetchone()[0] or 0.0
        
        saldo = total_receitas + total_despesas
        return total_receitas, total_despesas, saldo


    def relatorio_por_categoria(self, user_id, mes=None, ano=None):
        """Retorna gastos por categoria no período (lógica também está correta)"""
        # ... (este método pode ficar EXATAMENTE como estava na Etapa 3) ...
        query = '''
            SELECT categoria, SUM(valor) as total
            FROM transacoes
            WHERE tipo = 'despesa' AND user_id = ?
        '''
        params = [user_id]
        if mes:
            query += " AND strftime('%m', data) = ?"
            params.append(f"{mes:02d}")
        if ano:
            query += " AND strftime('%Y', data) = ?"
            params.append(str(ano))
        query += " GROUP BY categoria ORDER BY total ASC"
        
        self.cursor.execute(query, tuple(params))
        return self.cursor.fetchall()

    # --- Novos Métodos para Usuários ---

    def registrar_usuario(self, email, senha_plana):
        """Registra um novo usuário com senha hasheada."""
        try:
            # Gera o hash da senha
            senha_hash = bcrypt.hashpw(senha_plana.encode('utf-8'), bcrypt.gensalt())
            self.cursor.execute(
                "INSERT INTO usuarios (email, senha_hash) VALUES (?, ?)",
                (email, senha_hash)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Este erro ocorre se o email (UNIQUE) já existir
            return False 

    def verificar_usuario(self, email, senha_plana):
        """Verifica email e senha no login."""
        self.cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = ?", (email,))
        user_data = self.cursor.fetchone()
        
        if user_data:
            user_id, senha_hash = user_data
            # Verifica se a senha plana bate com o hash salvo
            if bcrypt.checkpw(senha_plana.encode('utf-8'), senha_hash):
                return user_id # Sucesso! Retorna o ID do usuário
        return None # Falha no login

    def buscar_usuario_por_id(self, user_id):
        """Busca um usuário pelo seu ID (usado pelo Flask-Login)."""
        self.cursor.execute("SELECT id, email FROM usuarios WHERE id = ?", (user_id,))
        return self.cursor.fetchone()

    # --- Métodos de Transação (AGORA PRECISAM DE user_id) ---

    def adicionar_transacao(self, tipo, descricao, valor, categoria, user_id):
        """Adiciona uma nova transação ligada a um user_id."""
        data = date.today().strftime('%Y-%m-%d')
        
        if tipo == 'despesa':
            valor = -abs(valor)
        
        try:
            self.cursor.execute('''
                INSERT INTO transacoes (data, tipo, descricao, valor, categoria, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (data, tipo, descricao, valor, categoria, user_id))
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar transação: {e}")

    def calcular_resumo(self, user_id, mes=None, ano=None):
        """Calcula o resumo, opcionalmente filtrando por mês e ano."""
        query_receitas = "SELECT SUM(valor) FROM transacoes WHERE tipo = 'receita' AND user_id = ?"
        query_despesas = "SELECT SUM(valor) FROM transacoes WHERE tipo = 'despesa' AND user_id = ?"
        params = [user_id]
        if mes:
            mes_str = f"{mes:02d}"
            query_receitas += " AND strftime('%m', data) = ?"
            query_despesas += " AND strftime('%m', data) = ?"
            params.append(mes_str)
        if ano:
            ano_str = str(ano)
            query_receitas += " AND strftime('%Y', data) = ?"
            query_despesas += " AND strftime('%Y', data) = ?"
            params.append(ano_str)
        self.cursor.execute(query_receitas, tuple(params))
        total_receitas = self.cursor.fetchone()[0] or 0.0
        self.cursor.execute(query_despesas, tuple(params))
        total_despesas = self.cursor.fetchone()[0] or 0.0
        saldo = total_receitas + total_despesas
        return total_receitas, total_despesas, saldo

    def ler_transacoes(self, user_id, mes=None, ano=None):
        """Lê transações, agora juntando o nome da conta (JOIN)"""
        query = '''
            SELECT t.*, c.nome as conta_nome 
            FROM transacoes t
            JOIN contas c ON t.conta_id = c.id
            WHERE t.user_id = ?
        '''
        params = [user_id]
        
        if mes:
            query += " AND strftime('%m', t.data) = ?"
            params.append(f"{mes:02d}")
        if ano:
            query += " AND strftime('%Y', t.data) = ?"
            params.append(str(ano))
            
        query += " ORDER BY t.data DESC"
        
        self.cursor.execute(query, tuple(params))
        return self.cursor.fetchall()

    def relatorio_por_categoria(self, user_id, mes=None, ano=None):
        """Retorna gastos por categoria, opcionalmente filtrando por mês e ano."""
        query = '''
            SELECT categoria, SUM(valor) as total
            FROM transacoes
            WHERE tipo = 'despesa' AND user_id = ?
        '''
        params = [user_id]
        if mes:
            query += " AND strftime('%m', data) = ?"
            params.append(f"{mes:02d}")
        if ano:
            query += " AND strftime('%Y', data) = ?"
            params.append(str(ano))
        query += " GROUP BY categoria ORDER BY total ASC"
        self.cursor.execute(query, tuple(params))
        return self.cursor.fetchall()

    def excluir_transacao(self, transacao_id, user_id):
        """Exclui uma transação se ela pertencer ao usuário."""
        try:
            self.cursor.execute(
                "DELETE FROM transacoes WHERE id = ? AND user_id = ?",
                (transacao_id, user_id)
            )
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao excluir transação: {e}")
            return False

    def buscar_transacao_por_id(self, transacao_id, user_id):
        """Busca uma transação específica do usuário pelo ID."""
        self.cursor.execute(
            "SELECT * FROM transacoes WHERE id = ? AND user_id = ?",
            (transacao_id, user_id)
        )
        row = self.cursor.fetchone()
        if row:
            # Retorna um dicionário para facilitar o uso no template
            return {
                'id': row[0],
                'data': row[1],
                'tipo': row[2],
                'descricao': row[3],
                'valor': row[4],
                'categoria': row[5],
                'user_id': row[6]
            }
        return None

    def atualizar_transacao(self, transacao_id, tipo, descricao, valor, categoria, user_id):
        """Atualiza uma transação se ela pertencer ao usuário."""
        try:
            if tipo == 'despesa':
                valor = -abs(valor)
            self.cursor.execute(
                '''UPDATE transacoes SET tipo=?, descricao=?, valor=?, categoria=?
                   WHERE id=? AND user_id=?''',
                (tipo, descricao, valor, categoria, transacao_id, user_id)
            )
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao atualizar transação: {e}")
            return False