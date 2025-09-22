import os
from threading import Thread
from flask import Flask, request, make_response, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv
from openai import OpenAI

# --- módulos do projeto
# (o db.py não é usado; mantendo só o que de fato é necessário)
from guided_mode import processar_ajuda_guiada
from database import (
    obter_usuario, criar_usuario, atualizar_usuario,
    marcar_finalizado, apagar_usuario, salvar_mensagem,
    obter_historico, criar_tabela_conversas
)

# -----------------------------------------------------------------------------
# Inicialização
# -----------------------------------------------------------------------------
load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# URL opcional para callback de status (coloque no Render se quiser)
STATUS_CALLBACK_URL = os.getenv("STATUS_CALLBACK_URL")

# -----------------------------------------------------------------------------
# Etapas do cadastro
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Envio de mensagens (com logs de diagnóstico)
# -----------------------------------------------------------------------------
def enviar_resposta_twilio(to, mensagem):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_NUMBER")  # ex.: whatsapp:+14155238886 (sandbox)

    if not all([account_sid, auth_token, from_number]):
        print("[Twilio] Variáveis ausentes:", {
            "TWILIO_ACCOUNT_SID": bool(account_sid),
            "TWILIO_AUTH_TOKEN": bool(auth_token),
            "TWILIO_WHATSAPP_NUMBER": bool(from_number),
        })
        return

    try:
        client = TwilioClient(account_sid, auth_token)
        kwargs = {
            "body": mensagem,
            "from_": from_number,
            "to": to
        }
        if STATUS_CALLBACK_URL:
            kwargs["status_callback"] = STATUS_CALLBACK_URL

        msg = client.messages.create(**kwargs)
        print("[Twilio] Enviado OK | SID:", msg.sid, "| to:", to, "| from:", from_number)
    except TwilioRestException as e:
        # Erros do Twilio vêm com status/código úteis (ex.: 63005 template, 63016 janela etc.)
        print("[Twilio] ERRO Twilio:", e.status, getattr(e, "code", None), str(e))
    except Exception as e:
        print("[Twilio] ERRO genérico:", str(e))

# -----------------------------------------------------------------------------
# Geração de resposta da IA
# -----------------------------------------------------------------------------
def gerar_resposta_scinti(pergunta, whatsapp_id):
    salvar_mensagem(whatsapp_id, "user", pergunta)

    historico = obter_historico(whatsapp_id)
    mensagens = [
        {"role": "system", "content": (
            "Você é *Scinti*, uma assistente virtual empática e inteligente, especializada em orientar jovens sobre suas carreiras. "
            "Seu papel é ajudar jovens a refletirem sobre suas aspirações profissionais, cursos, caminhos no mercado de trabalho, vocações e dúvidas sobre o futuro. "
            "Você não responde a perguntas fora desse escopo. Quando necessário, gentilmente informe que só pode responder sobre temas relacionados a carreira. "
            "Suas respostas são breves (até 500 tokens), acolhedoras, e devem incentivar o jovem a pensar mais, trazendo novas perguntas ou reflexões. "
            "Se houver pedidos diretos por cursos ou plano de estudos, construa as soluções solicitadas."
        )}
    ]
    mensagens.extend(historico)

    resp = openai_client.chat.completions.create(
        model="gpt-4",
        messages=mensagens,
        temperature=0.7,
        max_tokens=500
    )

    conteudo = resp.choices[0].message.content.strip()
    salvar_mensagem(whatsapp_id, "assistant", conteudo)
    return conteudo

# -----------------------------------------------------------------------------
# Webhook do WhatsApp (Twilio)
# -----------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = (request.form.get("Body") or "").strip()
    sender = request.form.get("From")  # vem como whatsapp:+55...
    message_sid = request.form.get("MessageSid")

    print("[Webhook] From:", sender, "| Body:", incoming_msg, "| SID:", message_sid)

    # TwiML de ACK imediato
    resp = MessagingResponse()
    resp.message("Recebido! Já estou processando sua resposta 😊")
    response = make_response(str(resp))
    response.headers["Content-Type"] = "application/xml"

    def processar_mensagem():
        try:
            if not incoming_msg:
                print("[Webhook] Body vazio; nada a processar.")
                return

            # Comandos utilitários
            if incoming_msg.lower() == "/reset":
                apagar_usuario(sender)
                enviar_resposta_twilio(sender, "Pronto! Seu cadastro foi reiniciado. Vamos começar: qual o seu nome completo?")
                return

            if incoming_msg.lower() == "/status":
                user = obter_usuario(sender) or {}
                enviar_resposta_twilio(sender, f"Status: {user}")
                return

            user = obter_usuario(sender)

            # Cadastro já finalizado → modo guiado + IA
            if user and user.get("finalizado"):
                resposta_metodologica = processar_ajuda_guiada(user, incoming_msg)
                if resposta_metodologica:
                    enviar_resposta_twilio(sender, resposta_metodologica)
                    return

                resposta_ia = gerar_resposta_scinti(incoming_msg, sender)
                enviar_resposta_twilio(sender, resposta_ia)
                return

            # Sem usuário → cria e pergunta nome
            if not user:
                criar_usuario(sender)
                enviar_resposta_twilio(sender, "Olá! Vamos começar. Qual o seu nome completo?")
                return

            # Fluxo das etapas
            etapa_atual = user["etapa"]
            for i, (campo, pergunta) in enumerate(etapas):
                if etapa_atual == campo:
                    resposta = incoming_msg

                    # validações simples (evitam ruído no cadastro)
                    if campo == "nome" and len(resposta.split()) < 2:
                        enviar_resposta_twilio(sender, "Pode me dizer seu *nome completo*? 🙂")
                        return
                    if campo == "idade" and not resposta.isdigit():
                        enviar_resposta_twilio(sender, "Me diga apenas a *idade* em números, por favor.")
                        return

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
                            "Pode me perguntar sobre profissões, mercado de trabalho, cursos técnicos ou superiores, "
                            "dúvidas sobre futuro profissional e mais. Estou aqui pra te ajudar no que for possível. "
                            "É só mandar uma pergunta!"
                        )
                        enviar_resposta_twilio(sender, mensagem_final)
                    return

            # fallback (não bateu nenhuma etapa)
            enviar_resposta_twilio(sender, "Algo deu errado. Envie /reset para recomeçar.")
        except Exception as e:
            print("[Webhook] ERRO no processamento:", str(e))

    Thread(target=processar_mensagem).start()
    return response

# -----------------------------------------------------------------------------
# (Diagnóstico) Callback de status do Twilio — loga o retorno do canal
# -----------------------------------------------------------------------------
@app.post("/_twilio_status")
def twilio_status():
    data = request.form.to_dict()
    print("[TwilioStatus]", data)
    return ("", 204)

# -----------------------------------------------------------------------------
# (Diagnóstico) Envio direto — testa credenciais/‘from’/opt-in sem passar pelo fluxo
# -----------------------------------------------------------------------------
@app.get("/_twilio_test")
def twilio_test():
    raw = (request.args.get("to") or "").strip()
    if not raw:
        return "use /_twilio_test?to=whatsapp:%2B55DDDNXXXXXXXX", 400

    # Normalização: trata "+" virando espaço na query
    to = raw.replace("whatsapp: ", "whatsapp:+")  # corrige 'whatsapp: 55...'
    if to.startswith("whatsapp:") and not to.startswith("whatsapp:+"):
        to = to.replace("whatsapp:", "whatsapp:+", 1)

    # Aceita também só dígitos e monta E.164 BR automaticamente (opcional)
    if to.isdigit():
        to = f"whatsapp:+{to}"

    sid  = os.getenv("TWILIO_ACCOUNT_SID")
    tok  = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_WHATSAPP_NUMBER")  # sandbox: whatsapp:+14155238886
    if not all([sid, tok, from_]):
        return {"ok": False, "step": "env_check"}, 500

    try:
        client = TwilioClient(sid, tok)
        msg = client.messages.create(body="Teste direto (sandbox).", from_=from_, to=to)
        return {"ok": True, "sid": msg.sid}
    except TwilioRestException as e:
        return {"ok": False, "step": "twilio_create", "status": e.status,
                "code": getattr(e, "code", None), "error": str(e)}, 400


# -----------------------------------------------------------------------------
# Tabelas sempre que subir o app
# -----------------------------------------------------------------------------
criar_tabela_conversas()

# -----------------------------------------------------------------------------
# Execução local / Render
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
