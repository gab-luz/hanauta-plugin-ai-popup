# Hanauta Nest — integração PyQt6

Implementação nativa da tela escolhida, com superfícies opacas, módulos arredondados e lavanda Hanauta. Não exige QWebEngine, imagens ou fontes de ícones externas. O desenho é uma aproximação funcional do mockup: ícones vetoriais substitutos, sem textura nem gradiente. O pacote não foi integrado ao repositório real, pois ele não foi fornecido nesta conversa.

## Arquivos e execução

- `hanauta_nest.py`: `Theme`, `NestView`, shell opcional `NestWindow` e demonstração offline.
- `requirements.txt`: dependência PyQt6.
- `preview.png`: captura real da implementação Qt, não do mockup.

Python 3.10 ou superior. Instale a dependência no ambiente virtual já utilizado pelo projeto. Execute `hanauta_nest.py` pelo mesmo interpretador para abrir a demonstração. Ao importar o módulo, nenhuma aplicação nem janela é criada. Não crie um segundo `QApplication` na aplicação existente.

## Instrução para o agente que fará a adaptação

Antes de editar, leia AGENTS.md e examine a arquitetura atual. Localize o popup, o shell compartilhado, os tokens do tema, provedores de ícones, fontes, internacionalização, controller de conversa, histórico, streaming e serviços de áudio/captura. Reutilize essas peças. Substitua a apresentação visual mantendo os contratos e recursos atuais. Evite criar backends, armazenamento ou gerenciadores de estado paralelos. Não remova HTML, Markdown, ferramentas, anexos, fontes ou cartões já suportados pelo projeto para encaixar esta demonstração.

Use `NestView` dentro do shell existente. `NestWindow` é somente uma alternativa independente: ela é frameless, Tool e always-on-top, e fecha ocultando a janela. Posicionamento, drag, resize, atalhos globais, regras i3, persistência de geometria e política de foco devem continuar sob responsabilidade do shell atual. Não copie as flags para uma view embutida.

## Contrato da view

| Sinal | Responsabilidade do código existente |
|---|---|
| `send_requested(str)` | Validar, aceitar e persistir o envio; iniciar o backend |
| `configure_requested()` | Abrir configurações/seletor do modelo |
| `history_requested()` | Abrir o histórico existente |
| `attachment_requested()` | Selecionar e validar anexos |
| `microphone_requested()` | Solicitar autorização e iniciar áudio |
| `screen_requested()` | Solicitar autorização e controlar contexto de tela |
| `close_requested()` | Aplicar a política de fechar/ocultar do shell |

| Método | Uso |
|---|---|
| `set_backend_state(connected, model_name='')` | Atualizar conexão e seleção |
| `set_busy(bool)` | Bloquear envio durante geração |
| `add_message(id, role, text, timestamp='')` | Adicionar mensagem com ID único |
| `update_message(id, text)` | Substituir o texto completo de uma mensagem existente |
| `clear_messages()` | Limpar apresentação ao trocar conversa |
| `clear_draft()` | Limpar rascunho após aceite do controller |
| `show_setup_card()` | Exibir aviso offline; ocultado ao conectar |
| `apply_theme(Theme(...))` | Aplicar paleta carregada pelo Hanauta |

Papéis aceitos: `user`, `assistant`, `system`. IDs duplicados geram `ValueError`; atualização de ID inexistente gera `KeyError`. O controller controla IDs e histórico. O identificador `hanauta:setup` é reservado para o cartão de configuração.

## Exemplo de conexão

```python
from hanauta_nest import NestView, Theme

# Dentro da inicialização da janela existente:
self.ai_view = NestView(parent=self)
self.existing_layout.addWidget(self.ai_view)
self.ai_view.configure_requested.connect(self.open_existing_model_settings)
self.ai_view.history_requested.connect(self.open_existing_history)
self.ai_view.send_requested.connect(self.accept_ai_message)
self.ai_view.close_requested.connect(self.hide)

# Atualize a view apenas depois da confirmação real do serviço:
self.ai_view.set_backend_state(True, "Nome do modelo")

# Método do controller: adapte nomes e tratamento de falhas ao projeto.
def accept_ai_message(self, text):
    if not self.backend.is_ready():
        self.ai_view.set_backend_state(False)
        return
    user_id = self.conversation.append_user(text)  # ID real do domínio
    self.ai_view.add_message(user_id, "user", text)
    self.ai_view.clear_draft()
    self.ai_view.set_busy(True)
    self.backend.start_generation(text)  # API assíncrona já existente
```

O exemplo representa contratos, não inventa a API concreta do Hanauta. Adapte as chamadas ao código encontrado. No término, cancelamento ou erro da geração, sempre libere `set_busy(False)`. Evite conexões duplicadas ao reabrir o popup. No aceite de envio, bloqueie imediatamente para impedir Enter duplo; não limpe o rascunho se a aceitação falhar.

## Streaming e histórico

Crie uma mensagem vazia de assistente quando a geração realmente começar. Acumule os deltas no controller e passe o texto completo a `update_message`. Consolide atualizações em intervalos de aproximadamente 30–60 ms para evitar relayout por token. Não execute requisições de rede na thread gráfica. Encaminhe eventos do worker por sinais Qt para slots de um QObject na thread GUI; jamais chame métodos de widgets diretamente do worker. Reutilize o cancelamento e o ciclo de vida atuais.

A demonstração usa `QLabel` em texto simples, com seleção e sem interpretação de HTML. Se o Hanauta já oferece Markdown, HTML, código, áudio ou fontes, substitua somente o conteúdo de cada bolha pelo renderer atual. Preserve a sanitização existente; não habilite HTML externo arbitrário. Para históricos grandes, reutilize o modelo/view ou a virtualização do projeto: esta versão cria um widget por mensagem.

As atualizações por streaming só acompanham o final se a rolagem estiver próxima do fim. A inserção de novas mensagens rola para o fim. Ao restaurar histórico, faça a adaptação para preservar a posição do usuário e evitar uma rolagem por item.

## Tema, acessibilidade e adaptação

Mapeie `Theme` para o resultado do loader compartilhado (`load_theme_palette` ou equivalente real). Os estilos ficam no componente, sem `QApplication.setStyleSheet`. O provedor `icon()` é um fallback desenhado com QPainter: substitua pelos ícones e pelo logotipo oficiais. O ícone de configuração usa sliders como substituto. Remova os poucos valores fixos de hover/disabled se o sistema fornecer tokens correspondentes. Traduções usam `self.tr()` para textos da interface; carregue o QTranslator existente antes de criar a view.

Layout padrão: 440×650 pixels lógicos; mínimo 400×580. O Qt trata escala de DPI; não multiplique dimensões novamente por devicePixelRatio. Verifique fontes e largura com escala de 125%, 150% e 200%. Substitua a família de fallback pelas fontes carregadas pela aplicação. Caso nomes de modelo sejam longos, aplique elisão e tooltip no adapter.

Enter solicita envio; Shift+Enter quebra linha. O envio fica desabilitado quando offline, ocupado ou com texto vazio. O controller mantém o rascunho até aceitar o envio. Microfone e captura apenas emitem sinais, sem iniciar dispositivos ou permissões. Não exiba checks de entrega offline: eles foram intencionalmente removidos do mockup.

## Verificação antes de integrar

Validados no ambiente de entrega: instanciação PyQt6 com plataforma offscreen, renderização, envio offline bloqueado, habilitação online, bloqueio durante geração, emissão do texto, limpeza e atualização incremental de mensagens. A captura mostra a implementação real. Falta validar no desktop i3/X11 do projeto, com fontes reais, regras de janela, foco, DPI e serviços existentes.

Critérios de aceite: preservar funções atuais; não bloquear a thread GUI; reabrir sem perder histórico nem duplicar eventos; manter rascunho em erro; atualizar tema; aceitar textos longos; navegar por teclado; pedir permissão antes de áudio/captura; não mostrar resposta fictícia sem backend.
