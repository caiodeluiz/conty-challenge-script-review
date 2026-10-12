# Uso de IA

IA foi usada para estruturar e escrever a API, a persistência SQLite, os testes e a documentação deste repositório. A revisão feita por IA conferiu o fluxo de estados, a retenção de versões e eventos, a comparação do prazo no fuso `America/Sao_Paulo`, o limite inclusivo do dia e a serialização das escritas no caminho HTTP.

Também foram executados os testes `unittest` locais descritos no README. Não houve revisão humana confirmada, integração externa ou validação de implantação.

A correção posterior ao primeiro checkpoint acrescentou estado por versão projetado do histórico e validação de Unicode. Foram aprovados 13 testes próprios e 30 casos adversariais da revisão independente por agentes de IA, incluindo histórico V1/V2 e rejeição de surrogate isolado com HTTP400. O coordenador também leu diretamente a produção, o incremento, os testes e os documentos e concluiu a revisão deste snapshot.
