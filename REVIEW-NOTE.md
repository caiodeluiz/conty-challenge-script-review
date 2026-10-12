# Nota ao avaliador

Comece por `script_review/service.py` e `tests/test_service.py`: ali estão as transições, o histórico versionado, a transação de escrita e os casos controlados de fuso/prazo. Depois veja `tests/test_http_api.py` para o fluxo completo pela API HTTP.

Ficaram de fora autenticação e papéis, interface, upload/vídeo e serviços externos. A escolha sobre versões após pedido e prazo está documentada no README; expiração e reabertura de um pedido vencido precisam de decisão de produto.
