28 — VW_FHIR_AUTH_ITEM
FHIR: Claim.item[] + ClaimResponse.item[]
Itens individuais da solicitação de autorização. Cada linha = 1 procedimento solicitado. Complementa a V06 (header da autorização) com o detalhe por procedimento. No FHIR, alimenta dois recursos: Claim.item[] (o que o hospital pediu) e ClaimResponse.item[] (o que a operadora respondeu).
SP-RC-002 (solicitar autorização)SP-RC-002 (validar procedimentos)SP-RC-007 (glosa por item)

Coluna Tasy (sugerida)	Tipo	Obrig.	FHIR Path	Descrição
NR_SEQ_AUTH_ITEM	NUMBER	Sim	Claim.item[].sequence	PK do item
NR_SEQ_AUTORIZACAO	NUMBER	Sim	Claim.id / ClaimResponse.request	FK para autorização (V06)
CD_PROCEDIMENTO	VARCHAR2(8)	Sim	Claim.item[].productOrService.coding[0].code	Código TUSS solicitado
DS_PROCEDIMENTO	VARCHAR2	Não	Claim.item[].productOrService.coding[0].display	Nome do procedimento
QT_SOLICITADA	NUMBER	Sim	Claim.item[].quantity.value	Quantidade solicitada pelo hospital
QT_AUTORIZADA	NUMBER	Não	ClaimResponse.item[].adjudication.value	Quantidade autorizada pela operadora (preenchida após resposta)
VL_UNITARIO	NUMBER(15,2)	Não	Claim.item[].unitPrice.value	Valor unitário do procedimento
VL_TOTAL_ITEM	NUMBER(15,2)	Não	Claim.item[].net.value	Valor total do item (QT × unitário)
CD_CID_JUSTIFICATIVA	VARCHAR2	Não	Claim.item[].diagnosisSequence	CID-10 justificativo deste item
IE_STATUS_ITEM	VARCHAR2	Sim	ClaimResponse.item[].adjudication.category	A=Aprovado, N=Negado, P=Pendente, PA=Aprovado Parcial
DS_MOTIVO_NEGATIVA	VARCHAR2	Não	ClaimResponse.item[].adjudication.reason	Motivo da negativa por item
CD_REGIAO_ANATOMICA	VARCHAR2	Não	Claim.item[].bodySite	Região anatômica (exigido para cirurgias)
CD_ESTABELECIMENTO	NUMBER	Sim	—	Tenant

-- Tabelas Tasy de origem (referência): -- AUTORIZACAO_PROCEDIMENTO (principal), AUTORIZACAO_CONVENIO (header = V06) -- Join: AUTORIZACAO_PROCEDIMENTO.NR_SEQ_AUTORIZACAO = AUTORIZACAO_CONVENIO.NR_SEQ_AUTORIZACAO -- Filtros: CD_ESTABELECIMENTO = :tenant, NR_SEQ_AUTORIZACAO = :authId -- Sync: CDC on INSERT/UPDATE (cada item pode mudar status individualmente) -- IMPORTANTE: Esta view é 1 Tasy → 2 FHIR: --   INSERT (solicitação criada)   → cria/atualiza Claim.item[] --   UPDATE (resposta da operadora) → cria/atualiza ClaimResponse.item[] -- Relação com V06: V06 = header (status geral, guia, validade) --                  V28 = line items (procedimentos individuais, qtd, status por item) -- Mapeamento: IE_STATUS_ITEM A→approved, N→denied, P→queued, PA→partial
No Tasy, solicitação e resposta ficam na mesma tabela (AUTORIZACAO_PROCEDIMENTO). No FHIR são recursos separados: Claim (pedido) e ClaimResponse (resposta). O adapter CDC deve tratar INSERT como Claim.item[] e UPDATE com status preenchido como ClaimResponse.item[].