import os
from threading import Thread
from twilio.rest import Client
from flask import Flask, request, make_response
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
from openai import OpenAI
from db import criar_tabela
from guided_mode import processar_ajuda_guiada  # novo
from database import (
    obter_usuario, criar_usuario, atualizar_usuario,
    marcar_finalizado, apagar_usuario, salvar_mensagem, 
    obter_historico, criar_tabela_conversas
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

def enviar_resposta_twilio(to, mensagem):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_NUMBER")  # Exemplo: "whatsapp:+14155238886"
    
    client = Client(account_sid, auth_token)
    client.messages.create(
        body=mensagem,
        from_=from_number,
        to=to
    )


def gerar_resposta_scinti(pergunta, whatsapp_id):
    salvar_mensagem(whatsapp_id, "user", pergunta)

    historico = obter_historico(whatsapp_id)
    mensagens = [
        {"role": "system", "content": (
            "Você é *Scinti*, uma assistente virtual empática e inteligente, especializada em orientar jovens sobre suas carreiras. "
            "Seu papel é ajudar jovens a refletirem sobre suas aspirações profissionais, cursos, caminhos no mercado de trabalho, vocações e dúvidas sobre o futuro. "
            "Você não responde a perguntas fora desse escopo. Quando necessário, gentilmente informe que só pode responder sobre temas relacionados a carreira. "
            "Suas respostas são breves (até 500 tokens), acolhedoras, e sempre incentivam o jovem a pensar mais, trazendo novas perguntas ou reflexões."
        )}
    ]
    mensagens.extend(historico)

    resposta = client.chat.completions.create(
        model="gpt-4",
        messages=mensagens,
        temperature=0.7,
        max_tokens=500
    )

    conteudo = resposta.choices[0].message.content.strip()
    salvar_mensagem(whatsapp_id, "assistant", conteudo)
    return conteudo


@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body").strip()
    sender = request.form.get("From")

    resp = MessagingResponse()
    resp.message("Recebido! Já estou processando sua resposta 😊")
    response = make_response(str(resp))
    response.headers["Content-Type"] = "application/xml"

    def processar_mensagem():
        if incoming_msg.lower() == "/reset":
            apagar_usuario(sender)
            return

        if incoming_msg.lower() == "/status":
            user = obter_usuario(sender)
            # Como já respondemos ao Twilio, apenas log ou log futuro
            return

        user = obter_usuario(sender)

        if user and user["finalizado"]:
            # novo: tenta responder com base na metodologia estruturada
            resposta_metodologica = processar_ajuda_guiada(sender, incoming_msg)  # novo
            if resposta_metodologica:  # novo
                enviar_resposta_twilio(sender, resposta_metodologica)  # novo
                return  # novo

            # novo: fallback para IA genérica
            resposta_ia = gerar_resposta_scinti(incoming_msg, sender)  # novo
            enviar_resposta_twilio(sender, resposta_ia)  # novo
            return

        if not user:
            criar_usuario(sender)
            enviar_resposta_twilio(sender, "Olá! Vamos começar. Qual o seu nome completo?")
            return

        etapa_atual = user["etapa"]
        for i, (campo, pergunta) in enumerate(etapas):
            if etapa_atual == campo:
                resposta = incoming_msg.strip()
                if campo in mapeamentos:
                    if resposta not in mapeamentos[campo]:
                        enviar_resposta_twilio(sender, "Opção inválida. Por favor, envie o número correspondente da lista.")
                        return
                    valor = mapeamentos[campo][resposta]
                else:
                    valor = resposta

                atualizar_usuario(sender, campo, valor)

                if i + 1 < len(etapas):
                    proxima_etapa = etapas[i + 1][0]
                    atualizar_usuario(sender, "etapa", proxima_etapa)
                    enviar_resposta_twilio(sender, etapas[i + 1][1])
                else:
                    marcar_finalizado(sender)
                    nome = valor if campo == "nome" else "jovem"
                    mensagem_final = (
                        f"Muito obrigado, {nome}! ✅ Seu cadastro foi finalizado.\n\n"
                        "👋 Eu sou a *Scinti*, sua assistente virtual de carreira!\n\n"
                        "Pode me perguntar sobre profissões, mercado de trabalho, cursos técnicos ou superiores, dúvidas sobre futuro profissional e mais.\n\n"
                        "Estou aqui pra te ajudar no que for possível. É só mandar uma pergunta!"
                    )
                    enviar_resposta_twilio(sender, mensagem_final)
                return

        enviar_resposta_twilio(sender, "Algo deu errado. Envie /reset para recomeçar.")

    Thread(target=processar_mensagem).start()
    return response

# Criação de tabelas deve ocorrer sempre
criar_tabela_conversas()

if __name__ == "__main__":
    app.run(port=5000)

