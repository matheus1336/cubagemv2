from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
import sqlite3
from datetime import datetime
import math

app = Flask(__name__)


# 🔹 Funções auxiliares
def norm_code(x):
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s

def to_float(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(" ", "").replace(",", ".")
    m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s)
    return float(m.group(0)) if m else 0.0



# 🔹 Criar banco SQLite se não existir
def criar_banco():
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cubagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_total REAL,
            peso_total REAL,
            data TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cubagem_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cubagem INTEGER,
            codigo TEXT,
            nome TEXT,
            quantidade INTEGER,
            comprimento REAL,
            largura REAL,
            altura REAL,
            volume REAL,
            peso REAL,
            FOREIGN KEY(id_cubagem) REFERENCES cubagem(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            Codigo TEXT PRIMARY KEY,
            Nome TEXT,
            Comprimento REAL,
            Largura REAL,
            Altura REAL,
            m3_total REAL,
            Peso REAL,
            Tipo TEXT
        )
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
            df = df.rename(columns={
                "Código": "Codigo",
                "C\u00f3digo": "Codigo",
                "Nome": "Nome",
                "Comprimento": "Comprimento",
                "Largura": "Largura",
                "Altura": "Altura",
                "M3": "m3_total",
                "m³": "m3_total",
                "m3": "m3_total",
                "Peso (kg)": "Peso",
                "peso": "Peso",
                "PESO": "Peso",
                "Tipo": "Tipo",
            })

            db_cols = ["Codigo", "Nome", "Comprimento", "Largura", "Altura", "m3_total", "Peso", "Tipo"]
            numeric_cols = ["Comprimento", "Largura", "Altura", "m3_total", "Peso"]

            for col in db_cols:
                if col not in df.columns:
                    if col in numeric_cols:
                        df[col] = 0.0
                    else:
                        df[col] = ''

            df["Codigo"] = df["Codigo"].apply(norm_code)
            df['Nome'] = df['Nome'].fillna('')
            df['Tipo'] = df['Tipo'].fillna('acessorio')

            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)

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

# 🔹 Rotas
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/buscar", methods=["GET"])
def buscar():
    termo = request.args.get("q", "").lower()
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura FROM produtos WHERE Nome LIKE ? OR Codigo LIKE ? LIMIT 50",
        (f"%{termo}%", f"%{termo}%")
    )
    results = cur.fetchall()
    conn.close()
    
    registros = []
    for row in results:
        registros.append({
            "Codigo": row[0],
            "Nome": row[1],
            "m3_total": row[2],
            "Peso": row[3],
            "Comprimento": row[4],
            "Largura": row[5],
            "Altura": row[6],
        })
    return jsonify(registros)

@app.route('/buscar_lista', methods=['POST'])
def buscar_lista():
    codigos = request.json.get('codigos', [])
    if not codigos:
        return jsonify([])

    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()

    placeholders = ','.join(['?'] * len(codigos))
    query = f"SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura, Tipo FROM produtos WHERE Codigo IN ({placeholders})"
    
    cur.execute(query, codigos)
    results = cur.fetchall()
    conn.close()
    
    registros = []
    for row in results:
        registros.append({
            "Codigo": row[0],
            "Nome": row[1],
            "m3_total": row[2],
            "Peso": row[3],
            "Comprimento": row[4],
            "Largura": row[5],
            "Altura": row[6],
            "Tipo": row[7]
        })
    return jsonify(registros)

@app.route("/cubagem/<int:id>")
def get_cubagem(id):
    conn = sqlite3.connect("cubagens.db")
    cur = conn.cursor()
    cur.execute("SELECT id, volume_total, peso_total, data FROM cubagem WHERE id=?", (id,))
    cubagem = cur.fetchone()
    if not cubagem:
        return jsonify({"erro": "Cubagem não encontrada"}), 404
    cur.execute("SELECT codigo, nome, quantidade, comprimento, largura, altura, volume, peso FROM cubagem_itens WHERE id_cubagem=?", (id,))
    itens = cur.fetchall()
    conn.close()
    return jsonify({
        "id": cubagem[0],
        "volume_total": cubagem[1],
        "peso_total": cubagem[2],
        "data": cubagem[3],
        "itens": [
            {
                "Codigo": i[0],
                "Nome": i[1],
                "Quantidade": i[2],
                "Comprimento": i[3],
                "Largura": i[4],
                "Altura": i[5],
                "m3_total": i[6],
                "Peso": i[7]
            } for i in itens
        ]
    })


@app.route("/cubagem", methods=["POST"])
def cubagem():
    conn = None
    try:
        itens = request.json.get("itens", [])
        conn = sqlite3.connect("cubagens.db")
        cur = conn.cursor()

        volume_total = 0.0
        peso_total = 0.0
        volume_para_caixas = 0.0
        itens_lista = []

        for item in itens:
            codigo = norm_code(item.get("codigo"))
            qtd = int(item.get("quantidade", 1))
            
            cur.execute("SELECT Codigo, Nome, m3_total, Peso, Comprimento, Largura, Altura, Tipo FROM produtos WHERE Codigo = ?", (codigo,))
            db_row = cur.fetchone()

            if not db_row:
                continue
            
            r = {
                "Codigo": db_row[0], "Nome": db_row[1], "m3_total": db_row[2], "Peso": db_row[3],
                "Comprimento": db_row[4], "Largura": db_row[5], "Altura": db_row[6], "Tipo": db_row[7]
            }

            volume_item = float(r["m3_total"]) * qtd
            volume_total += volume_item
            peso_total += float(r["Peso"]) * qtd

            item_type = r.get("Tipo", "").strip().lower()

            if item_type == "acessorio":
                caixa_15tp_capacidade = 0.12
                volume_para_caixas += qtd * caixa_15tp_capacidade
            elif item_type != "caixa individual":
                volume_para_caixas += volume_item

            itens_lista.append({
                "Codigo": r["Codigo"],
                "Nome": str(r.get("Nome", "")),
                "Comprimento": float(r.get("Comprimento", 0.0)),
                "Largura": float(r.get("Largura", 0.0)),
                "Altura": float(r.get("Altura", 0.0)),
                "m3_total": volume_item,
                "Peso": float(r.get("Peso", 0.0)) * qtd,
                "Quantidade": qtd
            })

        caixa_15tp_capacidade = 0.12
        num_caixas = 0
        if volume_para_caixas > 0:
            num_caixas = math.ceil(volume_para_caixas / caixa_15tp_capacidade)
        
        if num_caixas > 0:
            caixas_possiveis = [{
                "nome": f"{num_caixas}x Caixa 15TP",
                "capacidade": num_caixas * caixa_15tp_capacidade
            }]
        else:
            caixas_possiveis = []

        cur.execute("INSERT INTO cubagem (volume_total, peso_total, data) VALUES (?, ?, ?)",
                    (volume_total, peso_total, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cubagem_id = cur.lastrowid

        for item in itens_lista:
            cur.execute("""
            INSERT INTO cubagem_itens
            (id_cubagem, codigo, nome, quantidade, comprimento, largura, altura, volume, peso)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cubagem_id,
                item["Codigo"], item["Nome"], item["Quantidade"],
                item["Comprimento"], item["Largura"], item["Altura"],
                item["m3_total"], item["Peso"]
            ))
        conn.commit()

        return jsonify({
            "numero_cubagem": cubagem_id,
            "itens_encontrados": len(itens_lista),
            "volume_total": volume_total,
            "peso_total": peso_total,
            "caixas": caixas_possiveis,
            "itens": itens_lista
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(debug=True)
