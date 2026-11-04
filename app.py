import os
import sqlite3
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for, session
from google import genai
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'zegenti_secret_key_comercial_2026'

DB_NAME = 'database.db'

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    
    # Tabela de Usuários
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE, senha TEXT, nome TEXT)''')
    
    # Tabela de Clientes
    conn.execute('''CREATE TABLE IF NOT EXISTS clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT, nome TEXT, razao_social TEXT, 
                    cidade TEXT, estado TEXT, contato TEXT, 
                    telefone TEXT, celular TEXT, historico TEXT, ultima_interacao TEXT)''')
    
    # Tabela de Produtos
    conn.execute('''CREATE TABLE IF NOT EXISTS produtos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT, sku TEXT, nome TEXT, marca TEXT, preco REAL)''')
    
    # Tabela de Orçamentos (com suporte a empresa emissora)
    conn.execute('''CREATE TABLE IF NOT EXISTS orcamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER, itens_json TEXT, observacoes TEXT, total REAL, status TEXT, data TEXT, criado_por TEXT, empresa_emissora TEXT)''')
    
    # Tabela de Contatos / Atendimentos
    conn.execute('''CREATE TABLE IF NOT EXISTS contatos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER, tipo TEXT, resumo TEXT, data TEXT, usuario TEXT)''')
    
    # Criar usuário admin padrão se não existir
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        conn.execute("INSERT INTO usuarios (usuario, senha, nome) VALUES (?, ?, ?)", ('admin', '123456', 'Administrador Zegenti'))
        conn.commit()

    # Importação automática das planilhas da Rein Sistemas se o banco estiver vazio
    cur.execute("SELECT COUNT(*) FROM clientes")
    if cur.fetchone()[0] == 0 and os.path.exists('CLIENTES.xlsx'):
        try:
            df_c = pd.read_excel('CLIENTES.xlsx')
            for _, row in df_c.iterrows():
                conn.execute('''INSERT INTO clientes (codigo, nome, razao_social, cidade, estado, contato, telefone, celular, historico, ultima_interacao)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                             (str(row.get('Código', '')), str(row.get('Nome', '')), str(row.get('Razão Social', '')),
                              str(row.get('Cidade', '')), str(row.get('Estado', '')), str(row.get('Contato', '')),
                              str(row.get('Telefone', '')), str(row.get('Celular', '')), 'Importado da Rein Sistemas', 'Recente'))
            conn.commit()
        except Exception as e:
            print(f"Erro ao importar clientes: {e}")

    cur.execute("SELECT COUNT(*) FROM produtos")
    if cur.fetchone()[0] == 0 and os.path.exists('produtos.xlsx'):
        try:
            df_p = pd.read_excel('produtos.xlsx')
            sku_counter = 1000
            for _, row in df_p.iterrows():
                preco_val = row.get('Valor de Mercado Tabela Normal TODOS os Estoques', 0)
                if pd.isna(preco_val):
                    preco_val = 0.0
                else:
                    try:
                        preco_val = float(str(preco_val).replace('.', '').replace(',', '.'))
                    except:
                        preco_val = 0.0

                sku_val = str(row.get('SKU', ''))
                if not sku_val or sku_val == 'nan' or sku_val.strip() == '':
                    sku_val = f"ZG-{sku_counter}"
                    sku_counter += 1

                conn.execute('''INSERT INTO produtos (codigo, sku, nome, marca, preco)
                                VALUES (?, ?, ?, ?, ?)''',
                             (str(row.get('Codigo', '')), sku_val, str(row.get('Produto', '')),
                              str(row.get('Marca', '')), preco_val))
            conn.commit()
        except Exception as e:
            print(f"Erro ao importar produtos: {e}")

    conn.close()

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        
        db = get_db()
        user = db.execute('SELECT * FROM usuarios WHERE usuario = ? AND senha = ?', (usuario, senha)).fetchone()
        db.close()
        
        if user:
            session['usuario'] = user['usuario']
            session['nome'] = user['nome']
            return redirect(url_for('index'))
        else:
            erro = "Usuário ou senha incorretos."
            
    return render_template_string(LOGIN_TEMPLATE, erro=erro)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    novo_user = request.form['novo_usuario']
    nova_senha = request.form['nova_senha']
    novo_nome = request.form['novo_nome']
    
    db = get_db()
    try:
        db.execute('INSERT INTO usuarios (usuario, senha, nome) VALUES (?, ?, ?)', (novo_user, nova_senha, novo_nome))
        db.commit()
    except Exception as e:
        print(f"Erro ao criar usuário: {e}")
    db.close()
    return redirect(url_for('index'))

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    clientes = db.execute('SELECT * FROM clientes ORDER BY nome').fetchall()
    produtos = db.execute('SELECT * FROM produtos ORDER BY nome').fetchall()
    usuarios = db.execute('SELECT * FROM usuarios ORDER BY nome').fetchall()
    
    # Filtros de Histórico de Contatos
    filtro_cliente = request.args.get('filtro_cliente', '')
    filtro_tipo = request.args.get('filtro_tipo', '')
    filtro_busca = request.args.get('filtro_busca', '')
    
    query_contatos = '''SELECT co.*, c.nome as cliente_nome FROM contatos co 
                        JOIN clientes c ON co.cliente_id = c.id WHERE 1=1'''
    params = []
    
    if filtro_cliente:
        query_contatos += ' AND co.cliente_id = ?'
        params.append(filtro_cliente)
    if filtro_tipo:
        query_contatos += ' AND co.tipo = ?'
        params.append(filtro_tipo)
    if filtro_busca:
        query_contatos += ' AND (co.resumo LIKE ? OR c.nome LIKE ?)'
        params.append(f'%{filtro_busca}%')
        params.append(f'%{filtro_busca}%')
        
    query_contatos += ' ORDER BY co.id DESC LIMIT 100'
    contatos = db.execute(query_contatos, params).fetchall()
    
    orcamentos_raw = db.execute('''SELECT o.*, c.nome as cliente_nome FROM orcamentos o 
                                  JOIN clientes c ON o.cliente_id = c.id ORDER BY o.id DESC''').fetchall()
    orcamentos = []
    for o in orcamentos_raw:
        dic = dict(o)
        try:
            dic['itens_parsed'] = json.loads(o['itens_json'])
        except:
            dic['itens_parsed'] = []
        orcamentos.append(dic)
    
    ai_insights = "Analisando base comercial..."
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = "Você é a IA de vendas da Zegenti/ZGSecurity. Dê 2 dicas curtas e práticas de negociação B2B de TI."
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            ai_insights = response.text
        except Exception as e:
            ai_insights = "IA ativa e pronta para otimizar suas negociações."

    db.close()
    return render_template_string(HTML_TEMPLATE, clientes=clientes, produtos=produtos, orcamentos=orcamentos, contatos=contatos, usuarios=usuarios, insights=ai_insights, usuario=session.get('nome'))

@app.route('/add_orcamento', methods=['POST'])
def add_orcamento():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    cliente_id = request.form['cliente_id']
    empresa_emissora = request.form['empresa_emissora']
    observacoes = request.form.get('observacoes', '')
    status = request.form.get('status', 'Pendente')
    criado_por = session.get('nome')
    data_hoje = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    produto_ids = request.form.getlist('produto_id[]')
    quantidades = request.form.getlist('quantidade[]')
    precos = request.form.getlist('preco[]')
    fechados = request.form.getlist('fechado[]')
    
    itens_lista = []
    total_geral = 0.0
    
    for i in range(len(produto_ids)):
        if not produto_ids[i]:
            continue
        p_id = produto_ids[i]
        prod = db.execute('SELECT * FROM produtos WHERE id = ?', (p_id,)).fetchone()
        if not prod:
            continue
            
        qtd = float(quantidades[i]) if quantidades[i] else 1.0
        preco_unit = float(precos[i]) if precos[i] else float(prod['preco'])
        subtotal = qtd * preco_unit
        is_fechado = str(i) in fechados
        
        if status == 'Fechado / Vendido':
            if is_fechado:
                total_geral += subtotal
        else:
            total_geral += subtotal
            
        itens_lista.append({
            'num': len(itens_lista) + 1,
            'sku': prod['sku'],
            'produto': prod['nome'],
            'quantidade': qtd,
            'preco_unitario': preco_unit,
            'subtotal': subtotal,
            'fechado': is_fechado
        })
    
    db.execute('INSERT INTO orcamentos (cliente_id, itens_json, observacoes, total, status, data, criado_por, empresa_emissora) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
               (cliente_id, json.dumps(itens_lista), observacoes, total_geral, status, data_hoje, criado_por, empresa_emissora))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/add_contato', methods=['POST'])
def add_contato():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    cliente_id = request.form['cliente_id']
    tipo = request.form['tipo']
    resumo = request.form['resumo']
    usuario = session.get('nome')
    data_hoje = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    db.execute('INSERT INTO contatos (cliente_id, tipo, resumo, data, usuario) VALUES (?, ?, ?, ?, ?)',
               (cliente_id, tipo, resumo, data_hoje, usuario))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/duplicar_orcamento/<int:id>', methods=['POST'])
def duplicar_orcamento(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    orc = db.execute('SELECT * FROM orcamentos WHERE id = ?', (id,)).fetchone()
    if orc:
        data_hoje = datetime.now().strftime('%d/%m/%Y %H:%M')
        db.execute('INSERT INTO orcamentos (cliente_id, itens_json, observacoes, total, status, data, criado_por, empresa_emissora) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (orc['cliente_id'], orc['itens_json'], orc['observacoes'], orc['total'], 'Pendente', data_hoje, session.get('nome'), orc['empresa_emissora']))
        db.commit()
    db.close()
    return redirect(url_for('index'))

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Login - Zegenti CRM</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 flex items-center justify-center h-screen font-sans">
    <div class="bg-white p-8 rounded-xl shadow-md w-full max-w-md border border-gray-200">
        <h1 class="text-2xl font-bold text-gray-800 mb-2 text-center">ZEGENTI / ZGSECURITY</h1>
        <p class="text-sm text-gray-500 mb-6 text-center">Acesse o sistema comercial</p>
        {% if erro %}
        <div class="bg-red-50 border border-red-200 text-red-700 p-3 rounded mb-4 text-xs font-semibold">{{ erro }}</div>
        {% endif %}
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-gray-600 mb-1">Usuário:</label>
                <input type="text" name="usuario" required class="w-full p-2 border rounded text-sm">
            </div>
            <div>
                <label class="block text-xs font-semibold text-gray-600 mb-1">Senha:</label>
                <input type="password" name="senha" required class="w-full p-2 border rounded text-sm">
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white p-2.5 rounded text-sm font-bold hover:bg-blue-700">Entrar no Sistema</button>
        </form>
    </div>
</body>
</html>
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-