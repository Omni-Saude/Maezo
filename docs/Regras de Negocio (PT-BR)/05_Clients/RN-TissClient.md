# RN-TissClient - Cliente TISS Base

## Identificação
- **Nome da Classe**: `TissClient`
- **Pacote**: `com.hospital.revenuecycle.integration.tiss`
- **Tipo**: Cliente de Integração
- **Padrão TISS**: TISS 4.0 (Troca de Informações em Saúde Suplementar)

## Objetivo
Cliente base para integração com o padrão TISS da ANS (Agência Nacional de Saúde Suplementar), responsável por validações e operações fundamentais de comunicação com operadoras de saúde.

## Contexto de Negócio
O padrão TISS é **OBRIGATÓRIO** para operações de saúde suplementar no Brasil, estabelecido pela ANS. Este cliente fornece as funcionalidades básicas para:
- Submissão de guias (autorizações)
- Consulta de status de cobranças
- Validação de códigos de procedimento (TUSS/CBHPM)
- Validação de compatibilidade diagnóstico-procedimento

## Regras de Negócio

### RN-TISS-001: Submissão de Guia
**Descrição**: Submete uma guia de cobrança para a operadora.

**Entradas**:
- `claimId`: Identificador único da cobrança

**Processamento**:
1. Registra log da submissão
2. *(Implementação stub - aguardando desenvolvimento completo)*

**Saídas**:
- Log de operação

**Regulamentação**: ANS RN 305/2012 (Padrão TISS)

---

### RN-TISS-002: Consulta Status de Guia
**Descrição**: Consulta o status de processamento de uma guia na operadora.

**Entradas**:
- `claimId`: Identificador da cobrança

**Processamento**:
1. Registra log da consulta
2. *(Stub retorna "PENDING")*

**Saídas**:
- `status`: Status da guia (PENDING, APPROVED, DENIED, etc.)

**Status Possíveis** (TISS 4.0):
- `PENDING`: Aguardando processamento
- `APPROVED`: Aprovada
- `DENIED`: Negada (glosa)
- `PARTIAL`: Parcialmente aprovada
- `IN_REVIEW`: Em análise

---

### RN-TISS-003: Validação de Código de Procedimento
**Descrição**: Valida se um código de procedimento é válido segundo tabelas TUSS/CBHPM.

**Entradas**:
- `code`: Código do procedimento

**Processamento**:
1. Verifica se código não é nulo
2. Verifica se código não está vazio
3. *(Stub - implementação completa requer tabelas TUSS/CBHPM atualizadas)*

**Saídas**:
- `boolean`: true se válido, false caso contrário

**Tabelas de Referência**:
- **TUSS**: Terminologia Unificada da Saúde Suplementar
- **CBHPM**: Classificação Brasileira Hierarquizada de Procedimentos Médicos

**Regulamentação**:
- ANS RN 338/2013 (TUSS)
- AMB/CFM CBHPM 6ª Edição

---

### RN-TISS-004: Validação de Compatibilidade Diagnóstico-Procedimento
**Descrição**: Valida se um diagnóstico (ICD-10) é compatível com o procedimento solicitado.

**Entradas**:
- `diagnosis`: Código CID-10 do diagnóstico
- `procedure`: Código TUSS/CBHPM do procedimento

**Processamento**:
1. Verifica se diagnóstico não é nulo/vazio
2. Verifica se procedimento não é nulo/vazio
3. *(Stub - implementação completa requer matriz de compatibilidade ANS)*

**Saídas**:
- `boolean`: true se compatível, false caso contrário

**Matriz de Compatibilidade**:
A ANS mantém tabelas de compatibilidade CID-10 x TUSS que determinam:
- Procedimentos permitidos por diagnóstico
- Restrições de autorização
- Necessidade de auditoria prévia

**Regulamentação**: ANS RN 338/2013

---

## Integrações

### Sistemas Integrados
1. **Operadoras de Saúde**: Sistema de autorização e cobrança
2. **ANS**: Validação de tabelas e padrões
3. **Sistema Interno**: Gestão de guias e cobranças

### Dependências
- `lombok`: Logging automático
- `spring-boot`: Framework de injeção de dependência

---

## Padrão TISS - Especificações Técnicas

### Versões Suportadas
- **TISS 3.05.00**: Versão anterior (compatibilidade)
- **TISS 4.0**: Versão atual (em implementação)
- **TISS 4.01**: Atualizações recentes
- **TISS 4.03.03**: Versão mais recente (2024)

### Componentes TISS
1. **Organizacional**: Cadastros e vínculos
2. **Transacional**: Guias e demonstrativos
3. **Representação de Conceitos**: Terminologias e tabelas
4. **Comunicação**: Protocolos de troca

---

## Status de Implementação

### ⚠️ IMPLEMENTAÇÃO STUB
Esta classe está parcialmente implementada como **stub**. As funcionalidades reais requerem:

1. **Conexão com Operadoras**:
   - Endpoints de cada operadora
   - Autenticação e certificados digitais
   - Protocolo de comunicação (SOAP/REST)

2. **Tabelas Atualizadas**:
   - TUSS completo (milhares de códigos)
   - CBHPM atualizado
   - Matriz de compatibilidade CID-10 x TUSS

3. **Validações Completas**:
   - Parser de código de procedimento
   - Validação de estrutura (dígitos verificadores)
   - Regras de negócio específicas por tipo de guia

4. **Certificação Digital**:
   - Certificado A3 para assinatura XML
   - Timestamping para não-repúdio

---

## Próximos Passos

### Fase 1: Validações Offline
- [ ] Implementar parser de códigos TUSS
- [ ] Carregar tabelas TUSS/CBHPM em banco
- [ ] Implementar validação estrutural de códigos

### Fase 2: Integração com ANS
- [ ] Obter acesso ao webservice TISS da ANS
- [ ] Implementar validação online de códigos
- [ ] Sincronizar tabelas automaticamente

### Fase 3: Integração com Operadoras
- [ ] Mapear endpoints de operadoras principais
- [ ] Implementar autenticação por operadora
- [ ] Desenvolver adaptadores específicos

### Fase 4: Conformidade Completa
- [ ] Certificação digital A3
- [ ] Assinatura XML de guias
- [ ] Auditoria de submissões

---

## Referências Regulatórias

### ANS - Agência Nacional de Saúde Suplementar
- **RN 305/2012**: Instituição do Padrão TISS
- **RN 338/2013**: TUSS - Terminologia Unificada
- **RN 395/2016**: Atualizações TISS 3.0
- **RN 452/2020**: Atualizações TISS 4.0

### Acesso às Especificações
- Portal ANS: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar
- Download TISS: https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar/padrao-tiss

---

## Notas de Compliance

### ⚠️ CRÍTICO: Conformidade Legal
- O uso incorreto do padrão TISS pode resultar em **multas da ANS**
- Guias não conformes podem ser **automaticamente glosadas**
- É obrigatório manter **logs de auditoria** de todas as submissões

### Prazos de Atualização
- ANS publica atualizações do TISS **semestralmente**
- Operadoras têm 180 dias para se adequar
- Prestadores devem acompanhar publicações no DOU (Diário Oficial da União)

---

## Arquivo de Origem
`src/main/java/com/hospital/revenuecycle/integration/tiss/TissClient.java`
