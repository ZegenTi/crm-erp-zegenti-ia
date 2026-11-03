import os
import sqlite3
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for
from google import genai

app = Flask(__name__)

DB_NAME = 'database.db'

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    
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
    
    # Tabela de Orçamentos com campos de itens fechados e status expandido
    conn.execute('''CREATE TABLE IF NOT EXISTS orcamentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER, itens TEXT, itens_fechados TEXT, total REAL, status TEXT, data TEXT)''')
    
    conn.commit()
    
    # Importação automática das planilhas da Rein Sistemas se o banco estiver vazio
    cur = conn.cursor()
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
            for _, row in df_p.iterrows():
                preco_val = row.get('Valor de Mercado Tabela Normal TODOS os Estoques', 0)
                if pd.isna(preco_val):
                    preco_val = 0.0
                else:
                    try:
                        preco_val = float(str(preco_val).replace('.', '').replace(',', '.'))
                    except:
                        preco_val = 0.0

                conn.execute('''INSERT INTO produtos (codigo, sku, nome, marca, preco)
                                VALUES (?, ?, ?, ?, ?)''',
                             (str(row.get('Codigo', '')), str(row.get('SKU', '')), str(row.get('Produto', '')),
                              str(row.get('Marca', '')), preco_val))
            conn.commit()
        except Exception as e:
            print(f"Erro ao importar produtos: {e}")

    conn.close()

init_db()

@app.route('/')
def index():
    db = get_db()
    clientes = db.execute('SELECT * FROM clientes').fetchall()
    produtos = db.execute('SELECT * FROM produtos').fetchall()
    orcamentos = db.execute('''SELECT o.*, c.nome as cliente_nome FROM orcamentos o 
                              JOIN clientes c ON o.cliente_id = c.id ORDER BY o.id DESC''').fetchall()
    
    ai_insights = "Analisando base comercial..."
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = "Você é a IA de vendas da Zegenti/ZGSecurity. Dê 2 dicas curtas e práticas de follow-up com base em um sistema comercial B2B de TI."
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            ai_insights = response.text
        except Exception as e:
            ai_insights = "IA ativa e pronta para otimizar suas negociações."

    db.close()
    return render_template_string(HTML_TEMPLATE, clientes=clientes, produtos=produtos, orcamentos=orcamentos, insights=ai_insights)

@app.route('/add_orcamento', methods=['POST'])
def add_orcamento():
    db = get_db()
    cliente_id = request.form['cliente_id']
    itens = request.form['itens']
    itens_fechados = request.form.get('itens_fechados', 'Nenhum item sinalizado')
    total = float(request.form['total'])
    status = request.form.get('status', 'Pendente')
    db.execute('INSERT INTO orcamentos (cliente_id, itens, itens_fechados, total, status, data) VALUES (?, ?, ?, ?, ?, ?)',
               (cliente_id, itens, itens_fechados, total, status, '2026-11-03'))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/duplicar_orcamento/<int:id>', methods=['POST'])
def duplicar_orcamento(id):
    db = get_db()
    orc = db.execute('SELECT * FROM orcamentos WHERE id = ?', (id,)).fetchone()
    if orc:
        db.execute('INSERT INTO orcamentos (cliente_id, itens, itens_fechados, total, status, data) VALUES (?, ?, ?, ?, ?, ?)',
                   (orc['cliente_id'], orc['itens'], orc['itens_fechados'], orc['total'], 'Pendente', '2026-11-03'))
        db.commit()
    db.close()
    return redirect(url_for('index'))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>CRM & ERP Zegenti - Comercial</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans">
    <div class="container mx-auto p-6 max-w-7xl">
        <header class="flex justify-between items-center mb-8 bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <div>
                <h1 class="text-2xl font-bold text-gray-800">ZEGENTI / ZGSECURITY — CRM & ERP Comercial</h1>
                <p class="text-sm text-gray-500">Gestão de Clientes, Produtos e Orçamentos com IA</p>
            </div>
            <div class="bg-indigo-50 border border-indigo-100 p-4 rounded-lg max-w-md">
                <span class="text-xs font-semibold text-indigo-600 uppercase tracking-wider block mb-1">🤖 Insights de Vendas (Gemini)</span>
                <p class="text-xs text-indigo-900">{{ insights }}</p>
            </div>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <!-- ORÇAMENTO -->
            <div class="bg-white p-6 rounded-xl shadow-sm md:col-span-1 border border-gray-200">
                <h2 class="text-lg font-semibold text-gray-700 mb-4">Emitir Novo Orçamento</h2>
                <form action="/add_orcamento" method="POST" class="space-y-3">
                    <select name="cliente_id" required class="w-full p-2 border rounded text-sm bg-white">
                        <option value="">Selecione o Cliente</option>
                        {% for c in clientes %}
                        <option value="{{ c.id }}">{{ c.nome }} ({{ c.cidade }})</option>
                        {% endfor %}
                    </select>
                    <div>
                        <label class="text-xs text-gray-500 font-medium">Itens Propostos:</label>
                        <textarea name="itens" placeholder="Descreva os produtos e quantidades..." required class="w-full p-2 border rounded text-sm h-20"></textarea>
                    </div>
                    <div>
                        <label class="text-xs text-gray-500 font-medium">Itens Fechados / Aprovados pelo Cliente:</label>
                        <input type="text" name="itens_fechados" placeholder="Ex: Apenas o Switch Aruba" class="w-full p-2 border rounded text-sm">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <input type="number" step="0.01" name="total" placeholder="Valor Total (R$)" required class="w-full p-2 border rounded text-sm">
                        <select name="status" class="w-full p-2 border rounded text-sm bg-white font-medium">
                            <option value="Pendente">Pendente</option>
                            <option value="Fechado / Vendido">Fechado / Vendido</option>
                            <option value="Cancelado">Cancelado</option>
                        </select>
                    </div>
                    <button type="submit" class="w-full bg-blue-600 text-white p-2 rounded text-sm font-semibold hover:bg-blue-700">Salvar e Emitir Orçamento</button>
                </form>
            </div>

            <!-- ORÇAMENTOS RECENTES -->
            <div class="bg-white p-6 rounded-xl shadow-sm md:col-span-2 border border-gray-200">
                <h2 class="text-lg font-semibold text-gray-700 mb-3">Orçamentos Emitidos</h2>
                <div class="overflow-x-auto max-h-96 overflow-y-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-gray-50 text-gray-500 uppercase">
                            <tr>
                                <th class="p-2">Cliente</th>
                                <th class="p-2">Itens Propostos / Fechados</th>
                                <th class="p-2">Total</th>
                                <th class="p-2">Status</th>
                                <th class="p-2 text-right">Ações</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y">
                            {% for o in orcamentos %}
                            <tr>
                                <td class="p-2 font-medium">{{ o.cliente_nome }}</td>
                                <td class="p-2">
                                    <span class="text-gray-800 font-medium">Proposta:</span> {{ o.itens }}<br>
                                    <span class="text-emerald-700 font-semibold">Fechado:</span> {{ o.itens_fechados }}
                                </td>
                                <td class="p-2 text-emerald-600 font-bold">R$ {{ "%.2f"|format(o.total) }}</td>
                                <td class="p-2">
                                    {% if o.status == 'Fechado / Vendido' %}
                                    <span class="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-[10px] font-semibold">{{ o.status }}</span>
                                    {% elif o.status == 'Cancelado' %}
                                    <span class="bg-red-100 text-red-800 px-2 py-0.5 rounded text-[10px] font-semibold">{{ o.status }}</span>
                                    {% else %}
                                    <span class="bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded text-[10px] font-semibold">{{ o.status }}</span>
                                    {% endif %}
                                </td>
                                <td class="p-2 text-right">
                                    <form action="/duplicar_orcamento/{{ o.id }}" method="POST" class="inline">
                                        <button type="submit" class="bg-gray-200 hover:bg-gray-300 text-gray-700 px-2 py-1 rounded text-[11px] font-medium" title="Duplicar Orçamento">📋 Duplicar</button>
                                    </form>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- LISTAGEM DE CLIENTES E PRODUTOS IMPORTADOS -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h2 class="text-lg font-semibold text-gray-700 mb-3">Clientes Cadastrados (Total: {{ clientes|length }})</h2>
                <div class="overflow-x-auto max-h-64 overflow-y-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-gray-50 text-gray-500 uppercase">
                            <tr>
                                <th class="p-2">Nome / Razão Social</th>
                                <th class="p-2">Cidade/UF</th>
                                <th class="p-2">Contato / Tel</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y">
                            {% for c in clientes %}
                            <tr>
                                <td class="p-2 font-medium">{{ c.nome }}<br><span class="text-gray-400">{{ c.razao_social }}</span></td>
                                <td class="p-2">{{ c.cidade }}/{{ c.estado }}</td>
                                <td class="p-2">{{ c.telefone }} / {{ c.celular }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h2 class="text-lg font-semibold text-gray-700 mb-3">Produtos Cadastrados (Total: {{ produtos|length }})</h2>
                <div class="overflow-x-auto max-h-64 overflow-y-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-gray-50 text-gray-500 uppercase">
                            <tr>
                                <th class="p-2">Produto / Descrição</th>
                                <th class="pr-2">Marca</th>
                                <th class="p-2">Preço Tabela</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y">
                            {% for p in produtos %}
                            <tr>
                                <td class="p-2 font-medium">{{ p.nome }}</td>
                                <td class="p-2 text-gray-500">{{ p.marca }}</td>
                                <td class="p-2 text-emerald-600 font-bold">R$ {{ "%.2f"|format(p.preco) }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
