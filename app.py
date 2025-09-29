from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
import sqlite3
from datetime import datetime
import math
# Importação para o Visualizador 3D
from py3dbp import Packer, Bin, Item

app = Flask(__name__)

# 🔹 Constantes e Funções Auxiliares (do sistema original)
CAIXA_ACESSORIOS_COMPRIMENTO = 0.36
CAIXA_ACESSORIOS_LARGURA = 0.36
CAIXA_ACESSORIOS_ALTURA = 0.64
CAIXA_ACESSORIOS_VOLUME = CAIXA_ACESSORIOS_COMPRIMENTO * CAIXA_ACESSORIOS_LARGURA * CAIXA_ACESSORIOS_ALTURA

def norm_code(x):
    s = str(x).strip()
    return s[:-2] if s.endswith(".0") else s

# 🔹 Funções do Banco de Dados (do sistema original, sem alterações)
def criar_banco():
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    # ... (código de criação de tabelas idêntico ao original)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cubagem (id INTEGER PRIMARY KEY AUTOINCREMENT, volume_total REAL, peso_total REAL, data TEXT)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cubagem_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, id_cubagem INTEGER, codigo TEXT, nome TEXT, quantidade INTEGER, comprimento REAL, largura REAL, altura REAL, volume REAL, peso REAL, FOREIGN KEY(id_cubagem) REFERENCES cubagem(id))
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (Codigo TEXT PRIMARY KEY, Nome TEXT, Comprimento REAL, Largura REAL, Altura REAL, m3_total REAL, Peso REAL, Tipo TEXT)
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_produtos_nome ON produtos (Nome)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_produtos_codigo ON produtos (Codigo)")
    conn.commit()
    conn.close()

criar_banco()

def popular_banco_de_dados():
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM produtos")
    if cur.fetchone()[0] == 0:
        print("Populando o banco de dados de produtos a partir do arquivo Excel...")
        try:
            df = pd.read_excel("produtos.xlsx")
            # ... (código de população do banco idêntico ao original)
            df = df.rename(columns={"Código": "Codigo", "C\u00f3digo": "Codigo", "Nome": "Nome", "Comprimento": "Comprimento", "Largura": "Largura", "Altura": "Altura", "M3": "m3_total", "m³": "m3_total", "m3": "m3_total", "Peso (kg)": "Peso", "peso": "Peso", "PESO": "Peso", "Tipo": "Tipo"})
            db_cols = ["Codigo", "Nome", "Comprimento", "Largura", "Altura", "m3_total", "Peso", "Tipo"]
            numeric_cols = ["Comprimento", "Largura", "Altura", "m3_total", "Peso"]
            for col in db_cols:
                if col not in df.columns: df[col] = 0.0 if col in numeric_cols else ''
            df["Codigo"] = df["Codigo"].apply(norm_code)
            df['Nome'], df['Tipo'] = df['Nome'].fillna(''), df['Tipo'].fillna('acessorio')
            for col in numeric_cols: df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
            df_to_insert = df[db_cols].drop_duplicates(subset=['Codigo'])
            df_to_insert.to_sql("produtos", conn, if_exists="append", index=False)
            print(f"{len(df_to_insert)} produtos inseridos no banco de dados.")
        except Exception as e:
            print(f"Erro ao popular o banco de dados: {e}")
        finally:
            conn.close()
    else:
        conn.close()

popular_banco_de_dados()

# 🔹 Rotas do Sistema de Cubagem Original 🔹
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/buscar", methods=["GET"])
def buscar():
    # ... (código da rota /buscar idêntico ao original)
    termo = request.args.get("q", "").lower()
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute("SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura FROM produtos WHERE Nome LIKE ? OR Codigo LIKE ? LIMIT 50", (f"%{termo}%", f"%{termo}%"))
    results = cur.fetchall()
    conn.close()
    registros = [{"Codigo": r[0], "Nome": r[1], "m3_total": r[2], "Peso": r[3], "Comprimento": r[4], "Largura": r[5], "Altura": r[6]} for r in results]
    return jsonify(registros)


@app.route('/buscar_lista', methods=['POST'])
def buscar_lista():
    # ... (código da rota /buscar_lista idêntico ao original)
    codigos = request.json.get('codigos', [])
    if not codigos: return jsonify([])
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(codigos))
    query = f"SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura, Tipo FROM produtos WHERE Codigo IN ({placeholders})"
    cur.execute(query, codigos)
    results = cur.fetchall()
    conn.close()
    registros = [{"Codigo": r[0], "Nome": r[1], "m3_total": r[2], "Peso": r[3], "Comprimento": r[4], "Largura": r[5], "Altura": r[6], "Tipo": r[7]} for r in results]
    return jsonify(registros)

@app.route("/cubagem/<int:id>")
def get_cubagem(id):
    # ... (código da rota /cubagem/<id> idêntico ao original)
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute("SELECT id, volume_total, peso_total, data FROM cubagem WHERE id=?", (id,))
    cubagem = cur.fetchone()
    if not cubagem: return jsonify({"erro": "Cubagem não encontrada"}), 404
    cur.execute("SELECT codigo, nome, quantidade, comprimento, largura, altura, volume, peso FROM cubagem_itens WHERE id_cubagem=?", (id,))
    itens = cur.fetchall()
    conn.close()
    return jsonify({"id": cubagem[0], "volume_total": cubagem[1], "peso_total": cubagem[2], "data": cubagem[3], "itens": [{"Codigo": i[0], "Nome": i[1], "Quantidade": i[2], "Comprimento": i[3], "Largura": i[4], "Altura": i[5], "m3_total": i[6], "Peso": i[7]} for i in itens]})

@app.route("/cubagem", methods=["POST"])
def cubagem():
    # ... (código da rota /cubagem idêntico ao original)
    conn = None
    try:
        itens = request.json.get("itens", [])
        conn = sqlite3.connect("cubagens.db")
        cur = conn.cursor()
        volume_total, peso_total, volume_para_caixas = 0.0, 0.0, 0.0
        itens_lista = []
        for item in itens:
            codigo = norm_code(item.get("codigo"))
            qtd = int(item.get("quantidade", 1))
            cur.execute("SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura, Tipo FROM produtos WHERE Codigo = ?", (codigo,))
            db_row = cur.fetchone()
            if not db_row: continue
            r = {k: v for k, v in zip(["Codigo", "Nome", "m3_total", "Peso", "Comprimento", "Largura", "Altura", "Tipo"], db_row)}
            volume_item, peso_item = float(r["m3_total"]) * qtd, float(r["Peso"]) * qtd
            volume_total += volume_item
            peso_total += peso_item
            item_type = r.get("Tipo", "").strip().lower()
            comprimento, largura, altura = float(r.get("Comprimento", 0.0)), float(r.get("Largura", 0.0)), float(r.get("Altura", 0.0))
            if item_type == "acessorio":
                volume_para_caixas += volume_item
                comprimento, largura, altura = CAIXA_ACESSORIOS_COMPRIMENTO, CAIXA_ACESSORIOS_LARGURA, CAIXA_ACESSORIOS_ALTURA
            elif item_type != "caixa individual":
                volume_para_caixas += volume_item
            itens_lista.append({"Codigo": r["Codigo"], "Nome": str(r.get("Nome", "")), "Comprimento": comprimento, "Largura": largura, "Altura": altura, "m3_total": volume_item, "Peso": peso_item, "Quantidade": qtd, "Tipo": r["Tipo"]})
        num_caixas = math.ceil(volume_para_caixas / CAIXA_ACESSORIOS_VOLUME) if volume_para_caixas > 0 else 0
        caixas_possiveis = [{"qtd_caixas": num_caixas, "tipo_caixa": "Acessórios", "capacidade": num_caixas * CAIXA_ACESSORIOS_VOLUME}] if num_caixas > 0 else []
        cur.execute("INSERT INTO cubagem (volume_total, peso_total, data) VALUES (?, ?, ?)", (volume_total, peso_total, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cubagem_id = cur.lastrowid
        for item in itens_lista:
            cur.execute("INSERT INTO cubagem_itens (id_cubagem, codigo, nome, quantidade, comprimento, largura, altura, volume, peso) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (cubagem_id, item["Codigo"], item["Nome"], item["Quantidade"], item["Comprimento"], item["Largura"], item["Altura"], item["m3_total"], item["Peso"]))
        conn.commit()
        return jsonify({"numero_cubagem": cubagem_id, "itens_encontrados": len(itens_lista), "volume_total": volume_total, "peso_total": peso_total, "caixas": caixas_possiveis, "itens": itens_lista})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()


# 🔹 Rota do Visualizador 3D 🔹
@app.route("/pack", methods=["POST"])
def pack_items():
    items_data = request.json.get("items", [])
    packer = Packer()
    truck = Bin("Truck", 1200, 300, 300, 10000.0)  # Caminhão: 6m x 2m x 2m
    packer.add_bin(truck)

    for item_data in items_data:
        packer.add_item(Item(
            name=item_data.get("nome"),
            width=float(item_data.get("largura")),   # Convertido para cm no frontend
            height=float(item_data.get("altura")),  # Convertido para cm no frontend
            depth=float(item_data.get("profundidade")), # Convertido para cm no frontend
            weight=float(item_data.get("peso"))
        ))
    
    packer.pack(bigger_first=True, distribute_items=True)

    fitted_items, unfitted_items = [], []
    b = packer.bins[0]
    
    for item in b.items:
        fitted_items.append({
            "nome": item.name, "largura": float(item.width), "altura": float(item.height),
            "profundidade": float(item.depth),
            "posicao": {"x": float(item.position[0]), "y": float(item.position[1]), "z": float(item.position[2])}
        })
    for item in b.unfitted_items:
        unfitted_items.append(item.name)

    return jsonify({"fitted_items": fitted_items, "unfitted_items": unfitted_items})

if __name__ == "__main__":
    app.run(debug=True)
