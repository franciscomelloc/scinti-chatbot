import os
import sqlite3
from flask import Flask, request, make_response
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
from openai import OpenAI
from database import (
    obter_usuario, criar_usuario, atualizar_usuario,
    marcar_finalizado, apagar_usuario
)


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
DB_PATH = "chatbot.db"

etapas = [
    ("nome", "Qual o seu nome completo?"),
    ("idade", "Quantos anos você tem?"),
    ("genero", "Com qual identidade de gênero você se identifica?\n1. Mulher\n2. Homem\n3. Pessoa não binária\n4. Prefere não dizer")
]

mapeamentos = {
    "genero": {
        "1": "Mulher",
        "2": "Homem",
        "3": "Pessoa não binária",
        "4": "Prefere não dizer"
    }
}

def criar_tabela():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS usuarios")
    cursor.execute("""
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            whatsapp_id TEXT UNIQUE,
            nome TEXT,
            idade TEXT,
            genero TEXT,
            etapa TEXT,
            finalizado INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def obter_usuario(whatsapp_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE whatsapp_id = ?", (whatsapp_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def criar_usuario(whatsapp_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO usuarios (whatsapp_id, etapa, finalizado) VALUES (?, ?, 0)", (whatsapp_id, "nome"))
    conn.commit()
    conn.close()

def atualizar_usuario(whatsapp_id, campo, valor):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE usuarios SET {campo} = ? WHERE whatsapp_id = ?", (valor, whatsapp_id))
    conn.commit()
    conn.close()

def marcar_finalizado(whatsapp_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET finalizado = 1 WHERE whatsapp_id = ?", (whatsapp_id,))
    conn.commit()
    conn.close()

def apagar_usuario(whatsapp_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE whatsapp_id = ?", (whatsapp_id,))
    conn.commit()
    conn.close()

def gerar_resposta_scinti(pergunta):
    prompt = f"""
    Você é Scinti, uma assistente virtual especializada em orientar jovens sobre suas carreiras. 
    Você só responde perguntas relacionadas a carreira, futuro profissional, cursos, mercado de trabalho, vocação ou caminhos profissionais. 
    Se a pergunta não for sobre isso, gentilmente diga que só pode ajudar com temas de carreira. 
    As respostas devem ter até 500 tokens. 
    Ajude com orientações, mas sempre continue a conversa com mais perguntas

    Um jovem perguntou: "{pergunta}"
    """

    resposta = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Você é Scinti, assistente de carreira empática e inteligente."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )

    return resposta.choices[0].message.content.strip()

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body").strip()
    sender = request.form.get("From")
    resp = MessagingResponse()

    if incoming_msg.lower() == "/reset":
        apagar_usuario(sender)
        resp.message("Cadastro reiniciado! Qual o seu nome completo?")
        response = make_response(str(resp))
        response.headers["Content-Type"] = "application/xml"
        return response

    if incoming_msg.lower() == "/status":
        user = obter_usuario(sender)
        if not user:
            resp.message("Você ainda não iniciou o cadastro.")
        else:
            resp.message(f"Etapa atual: {user['etapa']}")
        response = make_response(str(resp))
        response.headers["Content-Type"] = "application/xml"
        return response

    user = obter_usuario(sender)

    if user and user["finalizado"]:
        # Se já finalizou o cadastro, responde com a IA
        resposta_ia = gerar_resposta_scinti(incoming_msg)
        resp.message(resposta_ia)
        response = make_response(str(resp))
        response.headers["Content-Type"] = "application/xml"
        return response

    if not user:
        # Se o usuário não existe, cria novo
        criar_usuario(sender)
        resp.message("Olá! Vamos começar. Qual o seu nome completo?")
        response = make_response(str(resp))
        response.headers["Content-Type"] = "application/xml"
        return response

    etapa_atual = user["etapa"]
    for i, (campo, pergunta) in enumerate(etapas):
        if etapa_atual == campo:
            resposta = incoming_msg.strip()
            if campo in mapeamentos:
                if resposta not in mapeamentos[campo]:
                    resp.message("Opção inválida. Por favor, envie o número correspondente da lista.")
                    response = make_response(str(resp))
                    response.headers["Content-Type"] = "application/xml"
                    return response
                valor = mapeamentos[campo][resposta]
            else:
                valor = resposta

            atualizar_usuario(sender, campo, valor)

            if i + 1 < len(etapas):
                proxima_etapa = etapas[i + 1][0]
                atualizar_usuario(sender, "etapa", proxima_etapa)
                resp.message(etapas[i + 1][1])
            else:
                marcar_finalizado(sender)
                nome = user["nome"] or "jovem"
                mensagem_final = (
                    f"Muito obrigado, {nome}! ✅ Seu cadastro foi finalizado.\n\n"
                    "👋 Eu sou a *Scinti*, sua assistente virtual de carreira!\n\n"
                    "Pode me perguntar sobre profissões, mercado de trabalho, cursos técnicos ou superiores, dúvidas sobre futuro profissional e mais.\n\n"
                    "Estou aqui pra te ajudar no que for possível. É só mandar uma pergunta!"
                )
                resp.message(mensagem_final)

            response = make_response(str(resp))
            response.headers["Content-Type"] = "application/xml"
            return response

    # fallback
    resp.message("Algo deu errado. Envie /reset para recomeçar.")
    response = make_response(str(resp))
    response.headers["Content-Type"] = "application/xml"
    return response

if __name__ == "__main__":
    from db import criar_tabela
    criar_tabela()
    app.run(port=5000)

