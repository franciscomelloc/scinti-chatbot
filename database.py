import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Conexão com o banco de dados PostgreSQL
def conectar():
    dbname = os.getenv("SUPABASE_DB")
    user = os.getenv("SUPABASE_USER")
    password = os.getenv("SUPABASE_PASSWORD")
    host = os.getenv("SUPABASE_HOST")
    port = os.getenv("SUPABASE_PORT")

    if not all([dbname, user, password, host, port]):
        raise ValueError("Erro: uma ou mais variáveis de ambiente do banco de dados não estão definidas.")

    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
        cursor_factory=RealDictCursor
    )

def obter_usuario(whatsapp_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE whatsapp_id = %s", (whatsapp_id,))
    user = cur.fetchone()
    conn.close()
    return user

def criar_usuario(whatsapp_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO usuarios (whatsapp_id, etapa, finalizado)
        VALUES (%s, 'nome', FALSE)
        ON CONFLICT (whatsapp_id) DO NOTHING
    """, (whatsapp_id,))
    conn.commit()
    conn.close()

def atualizar_usuario(whatsapp_id, campo, valor):
    conn = conectar()
    cur = conn.cursor()
    query = f"UPDATE usuarios SET {campo} = %s WHERE whatsapp_id = %s"
    cur.execute(query, (valor, whatsapp_id))
    conn.commit()
    conn.close()

def marcar_finalizado(whatsapp_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET finalizado = 1 WHERE whatsapp_id = %s", (whatsapp_id,))
    conn.commit()
    conn.close()

def apagar_usuario(whatsapp_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE whatsapp_id = %s", (whatsapp_id,))
    conn.commit()
    conn.close()

def criar_tabela_conversas():
    conn = conectar()
    cur = conn.cursor()

    # Tabela de usuários (caso não tenha criado ainda)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            whatsapp_id TEXT UNIQUE NOT NULL,
            nome TEXT,
            idade TEXT,
            genero TEXT,
            etapa TEXT NOT NULL DEFAULT 'nome',
            finalizado BOOLEAN NOT NULL DEFAULT FALSE
        );
    """)

    # Tabela de conversas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversas (
            id SERIAL PRIMARY KEY,
            whatsapp_id TEXT NOT NULL,
            role TEXT NOT NULL,  -- 'user' ou 'assistant'
            content TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def salvar_mensagem(whatsapp_id, role, content):
    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversas (whatsapp_id, role, content) VALUES (%s, %s, %s)",
        (whatsapp_id, role, content)
    )
    conn.commit()
    conn.close()

def obter_historico(whatsapp_id, limite=10):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT role, content FROM conversas
        WHERE whatsapp_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """, (whatsapp_id, limite))
    mensagens = cur.fetchall()
    conn.close()
    return list(reversed(mensagens))
