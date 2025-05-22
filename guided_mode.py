from perguntas import PERGUNTAS_GUIADAS
from database import salvar_mensagem, obter_historico, atualizar_usuario

# Verifica a próxima pergunta que ainda não foi respondida na fase atual
def escolher_proxima_pergunta(fase, respondidas):
    for pergunta in PERGUNTAS_GUIADAS.get(fase, []):
        if pergunta["id"] not in respondidas:
            return pergunta
    return None

# Retorna a próxima fase do planejamento guiado
def proxima_fase(fase_atual):
    fases = list(PERGUNTAS_GUIADAS.keys())
    if fase_atual not in fases:
        return fases[0]
    index = fases.index(fase_atual)
    if index + 1 < len(fases):
        return fases[index + 1]
    return None  # já está na última fase

# Recupera os IDs de perguntas já respondidas na fase atual
def obter_respostas_por_fase(whatsapp_id, fase):
    historico = obter_historico(whatsapp_id, limite=50)
    return [msg["pergunta_id"] for msg in historico if msg.get("fase") == fase and msg["role"] == "user"]

# Lida com uma resposta do usuário no modo guiado
def processar_resposta_guiada(user, mensagem):
    fase = user.get("fase_guiada", "autoconhecimento")
    respondidas = obter_respostas_por_fase(user["whatsapp_id"], fase)

    proxima = escolher_proxima_pergunta(fase, respondidas)
    if not proxima:
        nova_fase = proxima_fase(fase)
        if nova_fase:
            atualizar_usuario(user["whatsapp_id"], "fase_guiada", nova_fase)
            return f"Ótimo! Agora vamos para a próxima etapa: *{nova_fase}*\n\n{PERGUNTAS_GUIADAS[nova_fase][0]['texto']}", nova_fase
        else:
            return "Você completou todas as etapas do planejamento guiado! Se quiser conversar sobre outro assunto de carreira, estou aqui! 😊", None

    salvar_mensagem(user["whatsapp_id"], "user", mensagem, fase=fase, pergunta_id=proxima["id"])
    return proxima["texto"], fase

# Alias para compatibilidade com app.py
processar_ajuda_guiada = processar_resposta_guiada
