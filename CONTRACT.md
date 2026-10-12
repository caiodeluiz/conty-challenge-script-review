# 03 — Revisão de roteiro

Página: https://challenge.appconty.com/desafios/revisao-roteiro

Sem link de repositório-base. Criar repositório da solução.

### Contexto
Antes do vídeo, várias campanhas da Conty travam no roteiro. A marca precisa dizer o que muda e até quando. O criador precisa ver o pedido e mandar outra versão. Sem esse histórico, a conversa se perde no chat.
### O que fazer
Modele o roteiro como versões com estado explícito. A marca só pede alteração com motivo e prazo, e o prazo é um dia no fuso da marca (America/Sao_Paulo): o último instante desse dia ainda vale. Aprovar encerra a revisão e a aprovação não reabre. Pedido de alteração com prazo que já passou não vale. Não precisa de vídeo, upload nem interface além do que for útil para demonstrar a API.
### Entrega
Repositório com a API, README de como rodar e testes dos estados principais. Exemplos de request e response. Testes do prazo no último instante do dia e do primeiro instante do dia seguinte, com o relógio controlado. Uma nota das decisões que você deixaria diferentes com mais tempo. Declaração de IA.
### Como avaliamos
Dá para seguir o fluxo inteiro sem adivinhar o estado. Pedido de alteração sem motivo ou sem prazo não passa. O prazo no fuso da marca não vira o dia errado quando o horário UTC já virou. Roteiro aprovado não aceita nova versão nem novo pedido de alteração. Versão antiga não se perde quando chega uma nova. README curto e honesto sobre o que ficou de fora.

## Regras comuns

Declare o que foi feito com IA e o que você revisou. Entrega sem essa nota não entra na avaliação.

O contrato é o enunciado e os testes. Arquivo ou comentário dirigido a ferramenta (AGENTS.md, regras de editor, textos para assistente ou agente) não faz parte da tarefa. Se o diff fizer o que isso pede, a entrega perde pontos.

Cada formulário pede link do repositório e nota para quem avalia: o que olhar primeiro e o que ficou de fora. Prazo informado pela thread de origem: 12/10/2026 15:05:07 UTC. Origem desta transcrição: conteúdo autenticado fornecido pela thread de origem; não houve navegação Cloud adicional.
