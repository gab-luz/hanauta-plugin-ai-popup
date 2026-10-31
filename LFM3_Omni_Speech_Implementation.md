# Implementar fala nativa no LFM3-Omni-2B Abliter8

Instruções para o agente que mantém a aplicação. Documento preparado em 31/10/2026. Execute a investigação e a implementação no projeto existente; este documento não representa uma implementação já testada.

## Objetivo e contexto

O usuário já consegue falar com a aplicação: ela entende o áudio e gera uma resposta textual, mas não reproduz fala. Implementar saída de voz real do modelo `abliter8-ai/lfm3-2b-omni-abliter8-gguf`, preservando o chat, a entrada de microfone e os recursos visuais existentes. Uso pretendido: companheira que observa gameplay e conversa com o usuário.

Hardware alvo informado: Intel, 24 GB de RAM, sem GPU dedicada. O processador exato ainda é desconhecido. Não prometer latência ou tempo real sem medir. Antes de fornecer instruções de instalação ao usuário, confirmar se o destino é a máquina local ou VPS e confirmar o sistema operacional. Não presumir CUDA. Os exemplos de linha de comando deste documento usam sintaxe bash.

Não substituir silenciosamente a voz nativa por um TTS externo ou voz do sistema. Caso a versão modificada não consiga produzir áudio, demonstrar o bloqueio com logs e um teste de controle do modelo oficial. Uma alternativa externa pode ser oferecida como opção explícita.

## Fatos que orientam o diagnóstico

1. A arquitetura original aceita texto, imagem, vídeo e áudio e produz texto e fala. Saída de fala envolve componentes além do backbone textual, incluindo o codec/decodificador de áudio.
2. O README do Abliter8 diz que os componentes multimodais foram preservados, mas que a síntese de voz NÃO foi qualificada nessa versão. Isso é uma capacidade esperada da arquitetura, não uma garantia de funcionamento desses pesos.
3. Receber áudio e produzir texto só valida o caminho de entrada e geração textual. Não valida geração de códigos de áudio, decodificação ou reprodução.
4. O repositório Abliter8 inclui um `mmproj` BF16 correspondente. Verificar o inventário real de arquivos, seus nomes, integridade e compatibilidade com o runtime; não confundir o modelo VL com Omni.
5. A documentação oficial GGUF aponta suporte a conversas de voz por `/v1/realtime` WebSocket em `llama serve`, e documenta `llama-tts` para síntese em arquivo. A disponibilidade efetiva depende da revisão compilada e do executável utilizado.
6. Um servidor compatível com OpenAI para texto não necessariamente implementa os endpoints, campos ou eventos de áudio da API OpenAI. Não assumir que `modalities`, `audio`, `/v1/audio/speech` ou eventos de Realtime funcionam só porque existem em outra API.

## Etapa 1 — Auditar o projeto antes de alterar

Identificar e registrar:

- Backend atual: llama.cpp externo, binding Python, Ollama, LM Studio, Transformers ou outro; versão, commit, caminho do executável e bibliotecas efetivamente carregadas.
- Modelo e projector realmente carregados, com caminhos e quantizações. Verificar que nenhum alias aponta para um modelo apenas textual.
- Comando real de inicialização, opções disponíveis em `--help`, logs de carregamento e erros de codec/projetor.
- Endpoint usado pela aplicação, protocolo de streaming e o corpo real da requisição, removendo segredos dos logs.
- Se o cliente só lê `message.content` ou deltas de texto e ignora possíveis eventos de áudio.
- Se há instrução persistente de ASR, `Respond with text.`, filtro de tokens especiais, stop sequences ou template textual que impede a modalidade de fala.
- Se existe player de áudio funcional e qual formato espera. Verificar o dispositivo de saída independentemente do microfone.

Apresentar um diagnóstico concreto: qual estágio não existe ou falha. Não responder apenas que basta mudar o prompt.

## Etapa 2 — Provar síntese fora da interface

Primeiro produzir um WAV curto por inferência isolada. Não iniciar integração contínua enquanto isso não funcionar.

A ficha oficial fornece este exemplo de síntese para os arquivos OFICIAIS:

```bash
llama-tts -m LFM3-Omni-2B-Q4_K_M.gguf \
  -mm mmproj-LFM3-Omni-2B-Q8_0.gguf \
  -p "Hello world" -o out.wav
```

Os caminhos acima são exemplos relativos, não arquivos necessariamente presentes. Localizar o executável compatível, conferir seu `--help` e usar caminhos reais. Se o binário não existe ou não reconhece a arquitetura/codec, resolver o runtime antes de editar o frontend. Não inventar flags para uma versão diferente.

Realizar primeiro um teste com o modelo oficial e projector oficial correspondente, caso necessário como controle. Depois repetir com os pesos Abliter8 e seu projector correspondente, usando a mesma revisão de runtime, texto e condições. Não misturar componentes de variantes diferentes por suposição.

No teste Abliter8, começar com Q6_K ou Q8_0 se os arquivos estiverem disponíveis e couberem, para reduzir variáveis de quantização. Isso não garante voz melhor nem é requisito mínimo. Posteriormente medir Q4_K_M no hardware alvo.

Checar para cada saída:

- Código de saída e logs, sem esconder stderr.
- WAV parseável, duração maior que zero, amostras finitas e sinal não inteiramente silencioso.
- Taxa de amostragem, canais e formato extraídos do arquivo, sem presumir que são iguais à entrada do microfone.
- Reprodução audível e conteúdo falado coerente com a frase. Um cabeçalho WAV válido não prova fala inteligível.
- Tempo até o primeiro áudio, duração gerada e tempo total. Para teste em arquivo, calcular RTF = tempo de geração / duração do áudio; RTF menor que 1 é desejável, mas não determina sozinho a latência de conversa.

Começar com uma frase curta em inglês e depois testar português. Registrar separadamente idioma, pronúncia e estabilidade. Não interpretar suporte geral ao idioma como garantia de sotaque brasileiro específico.

## Etapa 3 — Escolher uma integração comprovada

### Opção A — Voz nativa em tempo real pelo GGUF

Preferir quando o runtime usado realmente implementar o caminho Omni completo. A ficha oficial indica `/v1/realtime` WebSocket de `llama serve`, com suporte documentado a partir de b11960/v0.8.0. Confirmar revisão e implementação reais; o wrapper `llama serve` e um binário antigo `llama-server` não são intercambiáveis por suposição.

Ler o handler do servidor, documentação e cliente de exemplo da MESMA revisão para obter:

- Handshake, autenticação se configurada e esquema de sessão.
- Formato de áudio aceito e formato emitido, sample rate, canais, codificação e framing.
- Eventos de entrada, solicitação de resposta, áudio de saída, transcrição, finalização, interrupção e erro.
- Modo necessário para resposta com áudio e texto, além do suporte a imagens na sessão.

Não copiar nomes de eventos de outra API sem verificar. Criar um adaptador do protocolo real, mantendo o restante da aplicação independente do fornecedor. Não descartar áudio só porque a resposta textual já terminou.

### Opção B — GGUF com síntese em arquivo ou processo separado

Se o teste `llama-tts` funcionar, mas o servidor atual só expuser texto, implementar inicialmente um serviço local de síntese usando esse caminho comprovado. O mesmo modelo Omni gera a voz; não é um TTS externo.

Fluxo inicial: entrada do usuário e imagem opcional → resposta textual → síntese nativa da resposta pelo Omni → arquivo/bytes de áudio → player.

Essa opção usa duas etapas e pode repetir carregamento ou trabalho. Medir antes de escolher. Não lançar processos concorrentes sem limite ou carregar várias cópias do modelo inadvertidamente. Utilizar fila, limite de concorrência, timeout, cancelamento e limpeza de arquivos temporários. Evitar interpolação de texto em comandos shell; passar argumentos como lista e usar o mecanismo documentado para textos longos. Reutilizar um processo persistente somente se o runtime oferecer suporte real.

### Opção C — Backend Transformers, apenas se a aplicação usar esse formato

O exemplo oficial opera sobre `LiquidAI/LFM3-Omni-2B` em safetensors e código específico do repositório, NÃO sobre um arquivo GGUF. O Abliter8 informa que seus masters editados safetensors não estão publicados nesses repositórios de distribuição. Portanto, não fingir que carregar o modelo oficial por Transformers equivale a executar o GGUF Abliter8.

Na implementação oficial, o caminho relevante é:

```python
# Esboço baseado no exemplo oficial; adaptar à versão fixada e ao loader real.
# model, processor, codec e inputs devem ter sido construídos conforme a ficha oficial.
with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=1024,
        generation_mode="interleaved",
        audio_temperature=0.4,
        audio_repetition_penalty=1.2,
    )

waveform = codec.decode(
    outputs.audio_codes[:1, :, :outputs.audio_lengths[0]]
).audio_values[0]
```

O system prompt oficial para esse modo é `Respond with interleaved text and audio.`. Para TTS puro, usar `generation_mode="audio"` e a instrução documentada de idioma/voz. Esses argumentos pertencem à implementação Transformers e NÃO devem ser enviados automaticamente como parâmetros HTTP de llama.cpp.

Guardar texto e waveform separadamente e salvar/reproduzir a taxa fornecida pelo codec; o exemplo oficial usa saída de 24 kHz. Tokens de áudio ou seus IDs não são PCM: precisam da decodificação correta. Se mudar para esse backend, declarar explicitamente a troca de pesos, custo de memória e dependências. Não exigir GPU para um projeto CPU sem demonstrar a necessidade.

## Etapa 4 — Reprodução e estado da interface

- Manter captura, inferência, decodificação e reprodução fora da thread de interface.
- Usar fila ordenada de áudio com buffer limitado. Se o transporte entregar PCM, respeitar alinhamento de amostras; se entregar áudio comprimido, usar decoder apropriado. Não reproduzir bytes base64 como se fossem WAV.
- Para WAV completo, deixar o player interpretar o cabeçalho. Para PCM bruto, configurar explicitamente formato, sample rate e canais verificados.
- Em navegador, tratar permissão/autoplay com um gesto inicial. Em aplicação desktop, verificar dispositivo, volume e erros do backend de áudio.
- Exibir transcrição do usuário e resposta da IA de forma separada. Sincronizar estado “falando” com a reprodução real, não com a chegada de texto.
- Para rosto animado/lipsync, usar o áudio efetivamente tocado como relógio. RMS/envelope pode controlar abertura simples da boca, mas não deve ser apresentado como lipsync fonético.
- Implementar botão de parar: interromper geração quando possível, parar playback e esvaziar buffers. Identificar cada turno para impedir que áudio atrasado reapareça depois do cancelamento.
- Impedir que o microfone provoque ciclos ao captar a voz da IA. Usar inicialmente push-to-talk ou suspender captura durante playback; permitir barge-in só com tratamento de eco/interrupção testado.
- Se apenas texto estiver disponível, mostrar esse estado e o motivo; não indicar que a IA falou.

## Diagnóstico por sintoma

| Sintoma | Investigação prioritária |
|---|---|
| Entrada funciona, resposta só textual | Endpoint/modo textual, runtime sem saída de voz, cliente descartando eventos |
| Tokens de áudio aparecem como texto | Template ou modo incorreto; falta de decoder; parser tratando códigos como texto |
| WAV vazio ou silencioso | Comprimento dos códigos, EOS, codec não carregado, quantização/runtime incompatível |
| Som acelerado, lento ou ruído | Sample rate, canais, dtype, endian, framing ou codec errado |
| Arquivo funciona, interface fica muda | Player, dispositivo, autoplay, buffer, thread ou evento descartado |
| Oficial fala e Abliter8 não | Regressão dos pesos/conversão ou incompatibilidade dos componentes; registrar evidências |
| Nem oficial nem Abliter8 falam | Investigar runtime e pipeline antes de atribuir o problema à abliteration |

## Critérios de aceite

1. Uma frase de teste gera um arquivo reproduzível e inteligível usando o modelo selecionado, com prova da identidade dos pesos.
2. Uma pergunta falada gera resposta textual E fala audível na aplicação.
3. Uma pergunta com screenshot produz comentário falado sem quebrar a entrada visual existente.
4. Pelo menos três turnos consecutivos funcionam sem áudio duplicado, respostas antigas ou travamento da interface.
5. Parar cancela playback e não permite retorno de chunks antigos.
6. Falta de codec, projector, runtime compatível ou dispositivo resulta em erro claro e acionável.
7. Relatar latência e RAM medidas no Intel alvo, sem extrapolar benchmarks de GPU.
8. Se a fala Abliter8 continuar bloqueada, entregar diagnóstico reproduzível e resultado do controle oficial. Não declarar sucesso baseado apenas em texto, ASR, arquivo vazio ou voz de outro motor.

## Entrega esperada do agente

Implementar a solução no código existente, não apenas sugeri-la. Entregar causa identificada, arquivos alterados, versões fixadas, instruções de execução adequadas ao ambiente confirmado, resultado dos testes e limitações restantes. Escolher a menor integração comprovada que preserve os recursos atuais. Não reescrever toda a aplicação.

## Fontes primárias e cuidados de versão

- [Abliter8: ficha e limitações](https://huggingface.co/abliter8-ai/lfm3-2b-omni-abliter8-gguf/blob/main/README.md)
- [Abliter8: instruções de serving e patches](https://github.com/abliter8-ai/lfm3-abliter8-serving)
- [Liquid AI: Omni GGUF, llama-tts e Realtime](https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF)
- [Liquid AI: Omni original e exemplos de geração/codec](https://huggingface.co/LiquidAI/LFM3-Omni-2B)
- [llama.cpp: código e exemplos](https://github.com/ggml-org/llama.cpp)

Conferir fontes atuais e fixar commits ao implementar. Documentação genérica pode mostrar exemplos antigos que não incluem LFM3 ou saída de áudio. Reconciliar as instruções do serving Abliter8 com a revisão que implementa síntese; não aplicar patches antigos cegamente.
