from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
import sqlite3
from datetime import datetime

app = Flask(__name__)

# 🔹 Tabela de caixas disponíveis
caixas = [
    {"nome": "Caixa 12TP", "capacidade": 0.11},
    {"nome": "Caixa 15TP", "capacidade": 0.12},
    {"nome": "Caixa 19TP", "capacidade": 0.21},
    {"nome": "Caixa 22TP", "capacidade": 0.33},
    {"nome": "Caixa 26TP", "capacidade": 0.50},
    {"nome": "Caixa 30TP", "capacidade": 0.67},
]

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

def carregar_dados():
    df = pd.read_excel("produtos.xlsx")
    df = df.rename(columns={
        "Código": "Codigo",
        "C\u00f3digo": "Codigo",
        "M3": "m3_total",
        "m³": "m3_total",
        "m3": "m3_total",
        "Peso (kg)": "Peso",
        "peso": "Peso",
        "PESO": "Peso",
    })
    if "Codigo" not in df.columns:
        raise ValueError("A planilha precisa ter a coluna 'Codigo'.")
    df["Codigo"] = df["Codigo"].apply(norm_code)
    for col in ["Comprimento", "Largura", "Altura", "m3_total", "Peso"]:
        if col in df.columns:
            df[col] = df[col].apply(to_float)
    if "m3_total" not in df.columns:
        df["m3_total"] = (df["Comprimento"] * df["Largura"] * df["Altura"]) / 1_000_000
    if "Peso" not in df.columns:
        df["Peso"] = 0.0
    return df

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
    conn.commit()
    conn.close()

criar_banco()

# 🔹 Rotas
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/buscar", methods=["GET"])
def buscar():
    termo = request.args.get("q", "").lower()
    df = carregar_dados()
    mask = df.apply(lambda r: termo in str(r.get("Codigo","")).lower() or termo in str(r.get("Nome","")).lower(), axis=1)
    out = df.loc[mask, ["Codigo", "Nome", "m3_total", "Peso", "Comprimento", "Largura", "Altura"]].copy()
    registros = []
    for _, row in out.iterrows():
        registros.append({
            "Codigo": row["Codigo"],
            "Nome": str(row.get("Nome", "")),
            "Comprimento": float(row.get("Comprimento", 0.0)),
            "Largura": float(row.get("Largura", 0.0)),
            "Altura": float(row.get("Altura", 0.0)),
            "m3_total": float(row.get("m3_total", 0.0)),
            "Peso": float(row.get("Peso", 0.0)),
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
    try:
        itens = request.json.get("itens", [])
        df = carregar_dados()

        volume_total = 0.0
        peso_total = 0.0
        itens_lista = []

        for item in itens:
            codigo = norm_code(item.get("codigo"))
            qtd = int(item.get("quantidade", 1))
            row = df[df["Codigo"] == codigo]
            if row.empty:
                continue
            r = row.iloc[0]

            volume_total += float(r["m3_total"]) * qtd
            peso_total += float(r["Peso"]) * qtd

            itens_lista.append({
                "Codigo": r["Codigo"],
                "Nome": str(r.get("Nome", "")),
                "Comprimento": float(r.get("Comprimento", 0.0)),
                "Largura": float(r.get("Largura", 0.0)),
                "Altura": float(r.get("Altura", 0.0)),
                "m3_total": float(r.get("m3_total", 0.0)) * qtd,
                "Peso": float(r.get("Peso", 0.0)) * qtd,
                "Quantidade": qtd
            })

        caixas_possiveis = sorted(
            [c for c in caixas if c["capacidade"] >= volume_total],
            key=lambda x: x["capacidade"]
        )

        # 🔹 Salvar no SQLite
        conn = sqlite3.connect("cubagens.db")
        cur = conn.cursor()
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
        conn.close()

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

if __name__ == "__main__":
    app.run(debug=True)

