# guided_mode.py (novo com respostas generativas guiadas)

from database import salvar_mensagem, obter_historico, atualizar_usuario
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Lista sequencial de intenções pedagógicas
INTENCOES_GUIADAS = [
    {"fase": "autoconhecimento", "topico": "interesses", "descricao": "descubra o que o jovem gosta de fazer no tempo livre"},
    {"fase": "autoconhecimento", "topico": "valores", "descricao": "explore os valores mais importantes para o jovem no trabalho"},
    {"fase": "autoconhecimento", "topico": "motivacoes", "descricao": "entenda o que motiva o jovem a estudar ou trabalhar"},
    {"fase": "exploracao", "topico": "curiosidade", "descricao": "investigue que áreas ou carreiras despertam curiosidade"},
    {"fase": "exploracao", "topico": "realidade", "descricao": "investigue se o jovem conhece as condições do mercado de trabalho"},
    {"fase": "planejamento", "topico": "metas", "descricao": "ajude o jovem a refletir sobre seus objetivos profissionais de curto prazo"},
    {"fase": "planejamento", "topico": "organizacao", "descricao": "ajude a identificar o que precisa fazer para atingir suas metas"},
    {"fase": "acompanhamento", "topico": "checkin", "descricao": "verifique se ele está conseguindo aplicar o plano"},
    {"fase": "acompanhamento", "topico": "reflexao", "descricao": "convide o jovem a refletir sobre o que aprendeu até agora"}
]

def proxima_intencao(index_atual):
    if index_atual + 1 < len(INTENCOES_GUIADAS):
        return INTENCOES_GUIADAS[index_atual + 1], index_atual + 1
    return None, index_atual

def processar_ajuda_guiada(user, mensagem_usuario):
    whatsapp_id = user["whatsapp_id"]
    index_atual = int(user.get("intencao_index", 0))
    intencao = INTENCOES_GUIADAS[index_atual]

    historico = obter_historico(whatsapp_id)
    mensagens = [
        {"role": "system", "content": f"""
            Você é Scinti, uma assistente de carreira empática e inteligente.
            Seu papel é apoiar jovens em sua jornada de planejamento de carreira.
            Agora você deve ajudar com a seguinte intenção pedagógica:
            - Fase: {intencao['fase']}
            - Objetivo: {intencao['descricao']}

            Com base na mensagem anterior do jovem, faça uma resposta que:
            1. Demonstre escuta e empatia;
            2. Prossiga com a conversa de forma natural;
            3. Traga uma nova pergunta que estimule reflexão sobre o tema.

            Não faça perguntas diretas copiadas. Escreva como se estivesse dialogando com cuidado e atenção.
        """}
    ]
    mensagens += historico[-10:]  # mensagens recentes
    mensagens.append({"role": "user", "content": mensagem_usuario})

    resposta = client.chat.completions.create(
        model="gpt-4",
        messages=mensagens,
        temperature=0.7,
        max_tokens=500
    )

    conteudo = resposta.choices[0].message.content.strip()
    salvar_mensagem(whatsapp_id, "user", mensagem_usuario)
    salvar_mensagem(whatsapp_id, "assistant", conteudo)

    # Atualiza o index para a próxima intenção
    proxima, novo_index = proxima_intencao(index_atual)
    atualizar_usuario(whatsapp_id, "intencao_index", novo_index)

    return conteudo
