  
**PHILIPS TASY**

**Relatório de Análise das APIs**

| Versão | 2.0 |
| :---- | :---- |
| **Data** | 02 de fevereiro de 2026 |
| **Fonte** | OS3009072\_02\_12\_PHILIPS\_TIE\_APIS\_SWAGGER\_PDF\_V2\_2 (892 páginas) |
| **Swagger** | v1.0 (dezembro/2022) |

**Grupo AUSTA \+ AMH**

# **1\. O Que o é TASY, Inferido pelas APIs**

Combinando as três análises, o TASY se revela como a **combinação de cinco sistemas em um**:

| HIS/PEP | ERP Hospitalar | Centro de Comando | Motor de Compliance |
| :---- | :---- | :---- | :---- |
| Prontuário Eletrônico, Agenda, Internação | Suprimentos, Compras, Faturamento, Financeiro | Telehealth, UTI/ICCA, Scoring Clínico | SUS, ANS, CNES, PIX |

**\+ CME (Central de Material Esterilizado)**

## **1.1 Backbone Clínico e Administrativo**

As APIs expõem as **primitivas canônicas** de um sistema hospitalar: paciente (natural-person), atendimento (encounter-patient), profissional (physician), pedido/prescrição (prescription) e catálogo de procedimentos (procedure). Estes são objetos de integração de primeira classe.

## **1.2 ERP Hospitalar Completo**

O ciclo completo de suprimentos está modelado: cadastro de materiais → requisição → cotação → pedido de compra → entrega → movimentação de estoque → inventário consignado. O módulo financeiro cobre contas a pagar/receber, liquidação, lotes contábeis, movimentações de cartão de crédito e PIX.

## **1.3 Centro de Comando / Tele-UTI**

As 66 APIs de telehealth vão muito além de videochamadas. Incluem: admissão/transferência/alta remota, notas clínicas, integração laboratorial e microbiológica, e **um motor de scoring clínico** com 9 endpoints dedicados a pontuação de risco (sepsis, deterioração, readmissão, mortalidade, acuidade, ventilação mecânica).

## **1.4 Motor Regulatório Brasileiro**

Endpoints dedicados a: APAC (procedimentos de alta complexidade), CNES (cadastro de estabelecimentos), CNS (cartão SUS), GERPAC (oncologia/hemodiálise), transmissão para base nacional, e importação de beneficiários — quase todos **write-only**, confirmando que o TASY é o sistema de registro que envia dados para o governo.

# **2\. Mapa de Domínios Funcionais**

## **2.1 Os 16 Domínios por Tamanho**

| \# | Domínio | Endpoints | Perfil CRUD | Natureza |
| :---- | :---- | :---- | :---- | :---- |
| 1 | **Agendamento** | 122 | Completo \+ Workflows | Hub operacional |
| 2 | **Materiais e Estoque** | 93 | Completo | ERP core |
| 3 | **Faturamento e Cobrança** | 77 | Leitura pesada | Ciclo de receita |
| 4 | **Telehealth e ICCA** | 66 | Escrita pesada (72%) | Centro de comando |
| 5 | **Gestão de Pacientes** | 63 | Completo | Cadastro master |
| 6 | **CME (Esterilização)** | 63 | Completo \+ DELETE | Operacional |
| 7 | **Compras** | 56 | Completo | ERP core |
| 8 | **Convênios e Planos** | 50 | Leitura pesada | Referência |
| 9 | Entidade Legal | 40 | Leitura pesada | Cadastro master |
| 10 | Clínico/PEP | 31 | Escrita pesada | Integração clínica |
| 11 | Financeiro | 29 | Misto | ERP core |
| 12 | Preço Global de Materiais | 18 | Write-only | Carga de dados |
| 13 | Oftalmologia | 15 | Read-only | Especialidade |
| 14 | Regulatório/SUS | 16 | **Write-only (100%)** | Compliance |
| 15 | Gestão Médica | 16 | Leitura pesada | Referência |
| 16 | Farmácia | 11 | Escrita pesada | Operacional |

## **2.2 Classificação por Fluxo de Eventos**

| Fluxo de Eventos | Endpoints | Razão Escrita | Natureza |
| :---- | :---- | :---- | :---- |
| **Clínico** | 94 | 72% | Prescrições, resultados, alertas — alta frequência de escrita |
| **Agendamento** | 119 | 45% | Leitura/escrita equilibrada — consultas \+ booking |
| **Supply Chain** | 194 | 49% | O maior cluster — materiais \+ compras \+ estoque \+ CME |
| **Ciclo de Receita** | 104 | 34% | Leitura pesada — muitas consultas de saldo/pendências |
| **Regulatório** | 16 | **100%** | Totalmente write-only — submissões ao governo |
| **Cadastral** | 111 | 32% | Dados mestres — pacientes, médicos, convênios, empresas |

*Achado importante: O fluxo regulatório é 100% escrita, sem nenhum GET. Isso confirma que o TASY é a fonte da verdade (system of record) para dados regulatórios.*

# **3\. Padrões Arquiteturais Identificados**

## **3.1 Dois Estilos Misturados: REST \+ Comandos de Workflow**

As três análises convergem neste achado central. A superfície da API mistura:

* **CRUD puro (\~82% dos endpoints):** padrão REST com GET/POST/PUT/DELETE sobre recursos  
* **Comandos de workflow (\~18% dos endpoints):** verbos na URL (cancel, process, transfer, activate, settle, rectify, verify)

*Implicação prática: Integrações devem ser modeladas como workflows event-driven (BPMN/DMN), não como simples sincronização CRUD.*

## **3.2 Padrão "Push \+ Callback" para Integrações Assíncronas**

Nove endpoints seguem explicitamente o padrão de callback assíncrono:

| Operação | Callback de Sucesso | Callback de Erro |
| :---- | :---- | :---- |
| APAC Report | POST /api/apacReport/success | POST /api/apacReport/error |
| APAC Parameters | POST /api/performAPACParam/success | POST /api/performAPACParam/error |
| SUS GERPAC | POST /api/sus/gerpac/.../success | POST /api/sus/gerpac/.../error |
| Relatórios Paciente | POST /api/reportspatient/success | POST /api/reportspatient/error |
| PIX Transmissão | — | POST /api/pix/transmission/{id}/error |

*Implicação: Integrações com governo e PIX são pipelines assíncronos. O sistema externo deve implementar retry com idempotência e reportar status de volta ao TASY.*

## **3.3 Modelagem Multi-Estabelecimento**

O parâmetro establishment / establishmentId / establishmentCode aparece em **35 endpoints** distribuídos por billing, materiais, CME, departamentos, entidades legais, seguros e setores.

*Implicação: Uma única instalação TASY gerencia múltiplas unidades. Toda integração deve tratar o escopo de estabelecimento como parâmetro obrigatório.*

## **3.4 Soft Delete e Gestão de Status**

O TASY prefere **flags de status** (ACTIVE/INACTIVE) sobre deleções físicas para dados de referência. Endpoints explícitos de activate e inactivate existem para: seguros, materiais, marcas de material e conversões de material-convênio.

## **3.5 Gestão de Status com 21 Transições Idempotentes (PUT)**

Foram identificados 21 endpoints PUT que representam transições de estado idempotentes, incluindo:

* Ativação/inativação de seguros e materiais  
* Processamento de requisições de materiais e dispensação eletrônica  
* Atualização de status de cama e catraca  
* Atualização de transmissão CNS

*Estas são operações seguras para retry — um padrão importante para integrações resilientes.*

# **4\. Análise Profunda: Máquina de Estados do Agendamento**

O módulo de agendamento é o mais complexo do TASY, com **53 estados possíveis** para um agendamento. Esta é uma das máquinas de estado mais elaboradas encontradas em ERPs hospitalares.

## **4.1 Fluxo Principal**

PRESCHEDULE → PRESCHEDULE\_CONFIRMED → SCHEDULED → CONFIRMED → WAITING → IN\_ANAMNESIS → AWAITING\_CONSULTATION → IN\_CONSULTATION → SERVICED → FINISHED

## **4.2 Fluxos Alternativos**

* SCHEDULED → CANCELLED (com motivo)  
* SCHEDULED → RESCHEDULED → SCHEDULED  
* CONFIRMED → JUSTIFIED\_ABSENCE / NOT\_JUSTIFIED\_ABSENCE  
* WAITING → ADMIT\_AS\_PRIORITY (encaixe de urgência)

## **4.3 Canais de Agendamento Suportados**

PHONE\_NUMBER · WHATSAPP · INTERNET · SITE · EMAIL · PERSONALLY · HOTLINE · ODC · SCHEDULING\_BATCH\_DISPATCH · TELEPHONE\_SCHEDULING\_CENTER · APPOINTMENT\_FROM\_ANOTHER\_UNIT

*Oportunidade de IA: A presença de WHATSAPP e INTERNET como canais oficiais de agendamento abre caminho direto para um agente de IA conversacional que acesse estas APIs para booking automatizado.*

# **5\. Análise Profunda: Motor de Precificação de Materiais**

O TASY implementa uma **matriz de 36 combinações** para resolver o preço de materiais e medicamentos, combinando as fontes:

* **Brasindice** (preço de referência para medicamentos)  
* **SIMPRO** (preço de referência para materiais médicos)  
* **Tabela de Preço** (tabela interna do hospital)  
* **Custo Médio** (média ponderada de compras)  
* **Valor Cotado** (preço de cotação)  
* **Tabela Adicional** (sobretaxas)

## 

## **5.1 Estratégias de Resolução de Preço**

| Estratégia | Descrição |
| :---- | :---- |
| VALIDITY\_DATE\_LATEST\_DATE | Usar a fonte com data de vigência mais recente |
| ORDER\_OF\_ORIGIN | Seguir ordem de prioridade configurada |
| VALIDITY\_PRIORITY\_DATE | Priorizar por vigência e depois por prioridade |
| HIGHEST\_VALUE\_AMONG\_SOURCES | Usar o maior valor entre as fontes |

*Implicação para OPME: A análise de Pareto sobre OPME pode ser potencializada cruzando os dados de materialPrice (preço vigente), stockMovement (consumo real) e purchase/order (preço de compra) para identificar discrepâncias entre preço de tabela e custo real.*

# **6\. Análise Profunda: Scoring Clínico e Tele-UTI**

## **6.1 Endpoints de Scoring**

| Endpoint | Função Clínica |
| :---- | :---- |
| sepsis-score \+ sepsis-alert | Detecção precoce de sepse (protocolo Surviving Sepsis Campaign) |
| early-warning-score | NEWS/MEWS — escore de alerta precoce para deterioração |
| risk-of-death-score | Predição de mortalidade (tipo APACHE/SAPS) |
| risk-of-readmission-score | Risco de readmissão em 30 dias |
| sentry-score \+ sentry-smart-alert | Vigilância inteligente de deterioração |
| automated-acuity | Classificação automática de gravidade |
| vent-management | Protocolo de desmame de ventilação mecânica |

## **6.2 Modelo de Dados VentManagementDTO**

O DTO de gestão de ventilação mecânica é o mais detalhado clinicamente:

* **Parâmetros ventilatórios:** FiO2, PEEP, frequência respiratória, volume corrente, dias de ventilação  
* **Gasometria arterial:** pH, PaCO2, PaO2, HCO3, SatO2  
* **Avaliação SAT/SBT:** prontidão para teste de respiração espontânea, agitação, saturação, PEEP, FiO2, estabilidade hemodinâmica  
* **Sedação:** nível de sedação, holiday de sedação

*Para a AMH (gestão de UTIs), isso representa uma fonte de dados estruturada para alimentar algoritmos de IA para otimização de tempo em ventilação mecânica.*

# **7\. Integração com Sistemas Externos**

## **7.1 Mapa de Integrações**

| Sistema | Fornecedor | Função |
| :---- | :---- | :---- |
| **Micromedex** | IBM | Interações medicamentosas e justificativas |
| **Brasindice** | Brasindice | Preço de referência para medicamentos |
| **SIMPRO** | SIMPRO | Preço de referência para materiais médicos |
| **ICCA** | Philips | UTI / Bombas de Infusão (29 endpoints) |
| **PIX** | Banco Central | Pagamentos instantâneos (9 endpoints) |
| **SUS** | Ministério da Saúde | APAC, GERPAC, AIH/BPA |
| **ANS** | ANS | TUSS, TISS, registro de planos |
| **CNES** | DataSUS | Cadastro de estabelecimentos |

## **7.2 Profundidade da Integração ICCA**

A integração com Philips ICCA (IntelliSpace Critical Care & Anesthesia) é a mais profunda, com 29 endpoints:

* **Bombas de infusão:** start/finish/disconnect solution, interface management  
* **Medicamentos:** alertas, filtros Micromedex, lista de alergias, lista de doenças  
* **Ordens clínicas:** importação por categoria (dieta, gases, material, procedimento)  
* **Dados do paciente:** importação e geração de dados vinculados

*O TASY funciona como hub de dados hospitalar onde dados de dispositivos de UTI fluem para o ERP para faturamento e documentação clínica. Crítico para operação de UTIs gerenciadas pela AMH.*

# **8\. Maturidade CRUD e System of Record**

## **8.1 Entidades com CRUD Completo (System of Record)**

Estas são as entidades onde o TASY **é a fonte da verdade** e oferece ciclo de vida completo:

| Entidade | GET | POST | PUT | DELETE | Search | Workflow |  |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| schedules | 36 | 31 | 15 | 4 | ✗ | ✓ |  |
| purchase | 26 | 14 | 11 | 5 | ✗ | ✗ |  |
| cssd-management | 24 | 16 | 12 | 11 | ✗ | ✓ |  |
| telehealth | 6 | 27 | 4 | 0 | ✗ | ✓ |  |
| invoice | 13 | 6 | 2 | 1 | ✓ | ✗ |  |
| material | 12 | 4 | 5 | 2 | ✗ | ✓ |  |
| natural-person | 9 | 6 | 6 | 4 | ✗ | ✗ |  |
| encounter-patient | 7 | 3 | 4 | 2 | ✗ | ✗ |  |

## **8.2 Dados de Referência (Read-Only)**

Estas tabelas são mantidas externamente e apenas consultadas no TASY:

* **Catálogos de preço:** Brasindice (laboratórios, medicamentos, apresentações), SIMPRO  
* **Codificação:** TUSS, CNES, CNS  
* **Referência:** procedimentos, especialidades médicas, departamentos, moedas

## **8.3 Event Sinks (Write-Only)**

Estes endpoints apenas recebem dados, sem consulta:

* **Regulatório:** APAC, CNES, SUS/GERPAC, transmissão para base nacional  
* **Dispositivos:** PIX webhooks, bombas de infusão (ICCA start/stop)  
* **Operacional:** bed-control, turnstile, pharmacy dispensary, SMS logs  
* **Resultados:** pathology, laboratory results, report analytes

# **9\. Inconsistências e Sinais de Evolução**

As três análises convergem em identificar sinais de **múltiplas gerações de desenvolvimento**:

## **9.1 Naming Conventions Mistas**

| Padrão | Exemplos | Interpretação |
| :---- | :---- | :---- |
| kebab-case (131) | account-receivable, cssd-management | APIs mais recentes |
| camelCase (95) | materialTuss, stockMovement | APIs legadas |
| Duplicatas | insurance ↔ insurances | Times diferentes |
| Português residual | account-pacient, EM\_PROCESSAMENTO | Falta de revisão |

## **9.2 Tratamento de Erros Esparso**

| Código HTTP | Ocorrências | Observação |
| :---- | :---- | :---- |
| 200 | 172 | Resposta padrão para tudo (inclusive criações) |
| 400 | 69 | Erro de validação |
| 500 | 18 | Erro de servidor |
| 404 | 10 | Não encontrado (usado raramente) |
| **201** | **3** | Created — quase não utilizado (violação REST) |

# **10\. Oportunidades de Automação por IA**

## **10.1 Alta Prioridade**

| Oportunidade | APIs Relevantes | Impacto |
| :---- | :---- | :---- |
| **Agente WhatsApp para Agendamento** | 122 endpoints de scheduling \+ time-suggestions \+ waiting-list | Redução de ligações \+ melhoria na taxa de comparecimento |
| **Automação de Ciclo de Receita** | billing \+ insurance-authorization \+ denial-appeal (77+ endpoints) | Redução de glosas, aceleração de faturamento |
| **Otimização de Compras/OPME** | purchase (56) \+ materialPrice \+ stockBalance \+ consigned-inventory | Análise Pareto automatizada, negociação baseada em dados |
| **Scoring Clínico em Tempo Real** | 9 endpoints de scoring telehealth \+ ICCA alerts | Detecção precoce de deterioração em UTIs AMH |

## **10.2 Média Prioridade**

| Oportunidade | APIs Relevantes | Impacto |
| :---- | :---- | :---- |
| Reconciliação Financeira PIX | pix (9 endpoints) \+ account-receivable/payable | Automação de baixas e conciliação |
| Gestão Inteligente de Leitos | bed-control \+ encounter-patient \+ discharge | Otimização de ocupação e giro de leito |
| Compliance Regulatório Automatizado | 16 endpoints regulatórios (APAC, CNES, CNS, SUS) | Validação pré-submissão, redução de rejeições |
| Gestão de CME | cssd-management (63 endpoints) | Rastreabilidade completa de instrumentais |

## **10.3 Próximos Passos Recomendados**

1. **Mapear system-of-record por objeto** — definir para cada entidade qual sistema é a fonte da verdade  
2. **Criar política de mapeamento de IDs** — normalizar identificadores internos vs códigos externos  
3. **Separar integrações em event streams** — clínico, agendamento, supply chain, receita, regulatório, cadastral  
4. **Definir semântica de idempotência e retry** — usando endpoints de success/error como evidência  
5. **Implementar camada de abstração** — absorver inconsistências de naming e normalizar respostas

# **11\. Conclusão**

O TASY TIE Engine expõe uma superfície de integração **massiva e funcional** que cobre todo o ciclo de vida hospitalar. Com **770 endpoints**, **469 modelos de dados** e **326 enumerações**, é um dos ERPs hospitalares mais completos do mercado brasileiro.

**Os principais pontos de atenção para equipes de integração são:**

* **Complexidade do agendamento (53 estados)** exige modelagem cuidadosa  
* **Precificação de materiais (36 combinações)** requer entendimento profundo das regras de negócio  
* **Inconsistências de naming** demandando uma camada de abstração  
* **Padrão assíncrono** para integrações regulatórias exigindo implementação de callbacks  
* **Multi-estabelecimento** como parâmetro obrigatório em todas as integrações

Por outro lado, as **oportunidades de automação por IA** são significativas: desde agentes de agendamento via WhatsApp até motores de scoring clínico para gestão de UTIs, passando por otimização de compras e automação de ciclo de receita.

