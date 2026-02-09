# RN-GLOSA-002: Aplicação de Correções e Reenvio de Contas

## I. Identificação da Regra

**Código**: RN-GLOSA-002
**Nome**: Aplicação de Correções e Reenvio de Contas
**Versão**: 1.0.0
**Módulo**: Gestão de Glosas
**Processo de Negócio**: Correção e Reenvio de Contas Glosadas
**Data de Criação**: 2026-01-12
**Última Atualização**: 2026-01-12
**Autor**: Equipe de Revenue Cycle

## II. Definição e Propósito

### Definição
Define o processo sistemático de correção de contas glosadas e preparação para reenvio, incluindo correções de códigos, ajustes de valores, anexação de documentação e validação de contratos.

### Propósito
Maximizar taxa de recuperação de glosas através de correções precisas e tempestivas, garantindo conformidade com padrões TISS e reduzindo tempo de ciclo de receita.

### Escopo
Aplica-se a todas as contas com glosas identificadas que possuem potencial de correção e reenvio, abrangendo todas as operadoras e tipos de procedimentos.

## III. Descrição da Lógica de Negócio

### Fluxo Principal

1. **Recuperação de Dados da Conta**
   - Sistema consulta detalhes completos da conta no TASY ERP
   - Sistema converte dados para formato padronizado
   - Sistema valida integridade dos dados recebidos

2. **Roteamento por Código de Negação TISS**
   - Sistema identifica código de negação específico
   - Sistema seleciona estratégia de correção apropriada:
     - Código 01: Duplicidade
     - Código 03: Não autorizado
     - Código 04/08: Código incorreto
     - Código 05: Valor acima do contratado
     - Código 06: Falta de documentação
     - Código 09: CID incompatível

3. **Aplicação de Correção Específica**
   - Sistema executa correção baseada em lógica especializada
   - Sistema valida correção através de regras TISS
   - Sistema documenta todas as alterações realizadas

4. **Validação e Preparação para Reenvio**
   - Sistema verifica completude das correções
   - Sistema marca conta como pronta para reenvio ou necessitando revisão manual
   - Sistema registra data e tipo de reenvio

5. **Integração com TASY e Reenvio**
   - Sistema atualiza conta no TASY ERP
   - Sistema reenvia conta com correções aplicadas
   - Sistema gera nova identificação de conta corrigida

### Estratégias de Correção por Código

**Código 01 - Duplicidade**
1. Sistema busca contas similares no TASY
2. SE nenhuma conta similar encontrada:
   - Sistema registra evidência de unicidade
   - Sistema reenvia com comprovação
3. SENÃO:
   - Sistema anula conta duplicada
   - Sistema mantém conta original

**Código 04/08 - Código Incorreto**
1. Sistema valida código TUSS atual via TISS Client
2. SE código inválido:
   - Sistema marca para revisão manual de codificação
3. SENÃO:
   - Sistema reenvia com validação de código

**Código 05 - Valor Acima do Contratado**
1. Sistema recupera preço contratado da tabela de contratos
2. SE valor faturado > valor contratado:
   - Sistema ajusta valor para preço contratado
   - Sistema reenvia com valor corrigido
3. SENÃO:
   - Sistema reenvia com justificativa de valor

**Código 06 - Falta de Documentação**
1. Sistema anexa documentos encontrados pela busca de evidências
2. SE documentos disponíveis:
   - Sistema anexa à conta via TASY
   - Sistema reenvia com documentação completa
3. SENÃO:
   - Sistema marca para intervenção manual

**Código 09 - CID Incompatível**
1. Sistema valida compatibilidade CID-procedimento via TISS
2. SE incompatível:
   - Sistema busca CID compatível no prontuário
   - Sistema atualiza diagnóstico e reenvia
3. SENÃO:
   - Sistema reenvia com validação de compatibilidade

**Código 03 - Não Autorizado**
1. Sistema busca número de autorização em documentos
2. SE autorização encontrada:
   - Sistema atualiza conta com número
   - Sistema reenvia com autorização
3. SENÃO:
   - Sistema marca para solicitação de autorização

### Regras de Decisão

**RD-001: Correção de Duplicidade**
- SE contas similares encontradas = 0
- ENTÃO ação = "REENVIA_COM_EVIDENCIA"
- SENÃO ação = "ANULA_DUPLICATA"

**RD-002: Ajuste de Valor**
- SE valor_faturado > valor_contratado
- ENTÃO novo_valor = valor_contratado
- E ação = "REENVIA_COM_AJUSTE"
- SENÃO ação = "REENVIA_COM_JUSTIFICATIVA"

**RD-003: Validação de Código**
- SE código_válido = FALSO
- ENTÃO ação = "REQUER_REVISAO_MANUAL"
- E motivo = "Código TUSS inválido"
- SENÃO ação = "REENVIA_COM_VALIDACAO"

**RD-004: Completude de Documentação**
- SE documentos_disponíveis > 0
- ENTÃO anexar_documentos()
- E ação = "REENVIA_COM_DOCUMENTACAO"
- SENÃO ação = "REQUER_INTERVENCAO_MANUAL"

## IV. Variáveis e Parâmetros

### Variáveis de Entrada
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| claimId | String | Sim | Identificador único da conta no TASY |
| denialCode | String | Sim | Código de negação TISS (01-99) |
| denialCategory | String | Sim | Categoria da negação |
| foundDocuments | List | Não | Documentos de evidência disponíveis |
| correctionNotes | String | Não | Notas adicionais para correção |

### Variáveis de Saída
| Nome | Tipo | Descrição |
|------|------|-----------|
| correctionApplied | Boolean | Indica se correção foi aplicada com sucesso |
| correctionType | String | Tipo de correção realizada |
| correctionDetails | Map | Detalhes das correções efetuadas |
| correctedClaimId | String | Novo ID da conta corrigida |
| readyForResubmission | Boolean | Indica se conta está pronta para reenvio |
| resubmissionDate | LocalDateTime | Data/hora do reenvio |
| attachedDocuments | List | Lista de documentos anexados |

## V. Cálculos e Fórmulas

### Ajuste de Valor Contratual
```
valor_ajustado = MINIMO(valor_faturado, valor_contratado)
ajuste_realizado = valor_faturado - valor_ajustado

registro_ajuste = {
  valor_original: valor_faturado,
  valor_contratado: valor_contratado,
  valor_ajustado: valor_ajustado,
  diferença: ajuste_realizado
}
```

### Validação de Percentual de Pagamento Parcial
```
percentual_pago = (valor_pago / valor_esperado) × 100

classificação = CASO
  QUANDO percentual_pago < 50%
    ENTÃO "NEGACAO_SIGNIFICATIVA"
  QUANDO percentual_pago ≥ 50%
    ENTÃO "SUBPAGAMENTO"
FIM CASO
```

## VI. Validações e Restrições

### Validações de Entrada
- **VLD-001**: ID da conta deve existir no sistema TASY
- **VLD-002**: Código de negação deve ser válido conforme Tabela TISS 44
- **VLD-003**: Categoria de negação deve ser preenchida

### Restrições de Negócio
- **RST-001**: Correção de código TUSS requer validação via TISS Client
- **RST-002**: Ajuste de valor não pode exceder valor contratado
- **RST-003**: Anexação de documentos requer pelo menos 1 documento disponível
- **RST-004**: Reenvio só permitido após correção completa ou evidenciação

## VII. Exceções e Tratamento de Erros

### Cenários de Exceção

**EXC-001: Conta Não Encontrada no TASY**
- Sistema registra erro em log
- Sistema marca conta para investigação
- Sistema não interrompe processamento de lote

**EXC-002: Falha em Validação TISS**
- Sistema registra warning
- Sistema continua com validação local
- Sistema marca para revisão posterior

**EXC-003: Documentos Insuficientes**
- Sistema marca `readyForResubmission = false`
- Sistema registra motivo: "Documentação insuficiente"
- Sistema escalona para coleta de documentos

**EXC-004: Código de Negação Desconhecido**
- Sistema aplica correção genérica
- Sistema marca para revisão manual
- Sistema registra código desconhecido para análise

## VIII. Integrações de Sistemas

### Sistemas Integrados
| Sistema | Tipo | Operações |
|---------|------|-----------|
| TASY ERP | Bidirecional | Consulta detalhes conta, atualiza valores, reenvia contas |
| TISS Client | Saída | Valida códigos TUSS, valida compatibilidade CID-procedimento |
| Sistema de Documentos | Saída | Anexa documentos clínicos à conta |

### Operações TASY ERP
```yaml
Consulta:
  - getClaimDetails(claimId): Recupera dados completos da conta
  - searchSimilarClaims(claimId): Busca duplicatas
  - getContractedPrice(payerId, procedureCode): Obtém preço contratual
  - getCompatibleDiagnosis(claimId, procedureCode): Busca CID compatível

Atualização:
  - updateClaimAmount(claimId, newAmount): Ajusta valor da conta
  - updateClaimDiagnosis(claimId, diagnosisCode): Corrige CID
  - updateClaimAuthorization(claimId, authNumber): Adiciona autorização
  - attachDocumentToClaim(claimId, documentId, type): Anexa documento

Reenvio:
  - resubmitClaim(claimId): Reenvia conta corrigida
  - resubmitClaimWithEvidence(claimId, evidence): Reenvia com evidências
  - voidDuplicateClaim(claimId): Anula conta duplicada
```

## IX. Indicadores de Performance (KPIs)

### KPIs Monitorados
| KPI | Métrica | Meta | Descrição |
|-----|---------|------|-----------|
| Taxa de Correção Automática | % | 70% | Percentual de glosas corrigidas automaticamente sem intervenção |
| Tempo Médio de Correção | Horas | < 24h | Tempo desde identificação até reenvio corrigido |
| Taxa de Aceitação Pós-Correção | % | 85% | Percentual de contas aceitas após correção |
| Taxa de Reenvio Bem-Sucedido | % | 90% | Percentual de reenvios sem falhas técnicas |

## X. Conformidade Regulatória

### Normas Aplicáveis

**TISS - Padrão TISS 4.0**
- Tabela 44: Motivos de Glosa (códigos 01-99)
- Seção 3.2.1: Correção de Códigos de Procedimentos
- Conformidade: Sistema utiliza validação TISS para todos os códigos

**ANS - Resolução Normativa 395/2016**
- Art. 20: Prazo de 10 dias para correção e reenvio
- Art. 21: Documentação comprobatória obrigatória
- Conformidade: Sistema registra timestamps e anexa documentação automaticamente

**LGPD - Lei 13.709/2018**
- Art. 6º: Finalidade específica do tratamento
- Conformidade: Sistema processa apenas dados necessários para correção

**CFM - Resolução 1.821/2007**
- Prontuário eletrônico e documentação médica
- Conformidade: Sistema respeita integridade de dados clínicos

## XI. Notas de Migração

### Migração Camunda 7 → Camunda 8

**Complexidade de Migração**: 8/10 (Alta)

**Impactos Identificados**:

1. **Integração com TASY ERP**
   - Camunda 7: Cliente REST síncrono via Spring
   - Camunda 8: Requer job workers assíncronos
   - Ação: Implementar conectores externos ou use Zeebe HTTP worker

2. **Transações Complexas**
   - Camunda 7: Suporte a transações distribuídas via JTA
   - Camunda 8: Modelo de compensação via eventos
   - Ação: Implementar saga pattern para rollback de correções

3. **Anexação de Documentos**
   - Camunda 7: Processamento síncrono de lista de documentos
   - Camunda 8: Processar em paralelo via sub-processos
   - Ação: Refatorar para processamento paralelo de anexação

4. **Mapeamento de DTOs**
   - Camunda 7: Conversão inline de TasyClaimDTO para Map
   - Camunda 8: Serialização JSON automática
   - Ação: Manter DTOs serializáveis ou usar JSON diretamente

**Esforço Estimado**: 24-32 horas
- Refatoração de integrações TASY: 12h
- Implementação de saga pattern: 8h
- Testes de regressão: 8h
- Documentação de conectores: 4h

## XII. Mapeamento DDD (Domain-Driven Design)

### Bounded Context
**Nome**: Correção de Glosas (Glosa Correction)

### Agregados
- **Agregado Principal**: Conta Glosada
- **Entidades**:
  - Conta Glosada (raiz)
  - Correção Aplicada
  - Documento Anexado
- **Value Objects**:
  - Código de Negação TISS
  - Valor Monetário
  - Tipo de Correção
  - Status de Reenvio

### Eventos de Domínio
| Evento | Descrição | Dados |
|--------|-----------|-------|
| CorrecaoAplicada | Correção foi aplicada à conta | claimId, tipo correção, detalhes, timestamp |
| ContaReen viada | Conta foi reenviada à operadora | claimId, correctedClaimId, resubmissionDate |
| DocumentoAnexado | Documento foi anexado à conta | claimId, documentId, documentType |
| RevisaoManualRequerida | Conta requer intervenção humana | claimId, motivo |

### Linguagem Ubíqua
- **Correção**: Modificação aplicada para resolver negação
- **Reenvio**: Submissão de conta corrigida à operadora
- **Anexação**: Vinculação de documento à conta
- **Ajuste de Valor**: Correção de valor faturado para conformidade contratual
- **Evidenciação**: Fornecimento de provas documentais

## XIII. Metadados Técnicos

### Informações de Implementação
| Atributo | Valor |
|----------|-------|
| Classe Java | `ApplyCorrectionsDelegate` |
| Bean Spring | `applyCorrectionsDelegate` |
| Camunda Task Type | Service Task (JavaDelegate) |
| Idempotência | Não explícita (recomendado adicionar) |
| Escopo de Variáveis | PROCESS |

### Estatísticas de Código
| Métrica | Valor |
|---------|-------|
| Linhas de Código | 592 |
| Complexidade Ciclomática | 9/10 (Alta) |
| Métodos Públicos | 2 |
| Métodos Privados | 11 |
| Cobertura de Testes | 80% (estimado) |

### Performance
| Métrica | Valor Esperado | Valor Crítico |
|---------|----------------|---------------|
| Tempo de Execução | 200-500ms | > 2s |
| Uso de Memória | < 50MB | > 200MB |
| Taxa de Sucesso | > 90% | < 80% |
| Throughput | 100 correções/min | < 30 correções/min |

### Dependências Técnicas
- **Spring Framework**: Injeção de dependências
- **Camunda BPM 7.x**: Engine de workflow
- **TasyClient**: Cliente REST para TASY ERP
- **TissClient**: Cliente para validação TISS
- **Lombok**: Redução de boilerplate

### Tags de Busca
`glosa`, `correção`, `reenvio`, `TISS`, `códigos`, `documentação`, `ajuste-valor`, `duplicidade`, `CID`, `autorização`

---

**Próxima Revisão**: 2026-04-12
**Responsável pela Manutenção**: Equipe de Revenue Cycle
**Criticidade**: ALTA
