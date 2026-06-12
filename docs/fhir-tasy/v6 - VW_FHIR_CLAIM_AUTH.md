V06 - VW_FHIR_CLAIM_AUTH
Recurso FHIR: ClaimResponse (preAuth) Descricao: Autorizacoes de procedimentos junto a operadoras.
Processos que consomem:
SP-RC-002 (authorization.request_payer, authorization.pre_auth_review -> authorizationStatus, authorizationNumber, requiresAuth, approvedAmount, authorizedDays)
SP-RC-004 (validate_compatibility -> authorizationId)
SP-RC-006 (validate_claim -> authorizationRequired, authorizationPresent)
SP-RC-014 (verify_coverage)
Variaveis BPMN alimentadas: authNumber, authorizationNumber, authorizationStatus, authRequestDate, authDeadline, authorizationDeadline, denialReason, authorizedProcedure, authorizedQuantity, approvedAmount, authorizedAmount, authorizedDays, authorizationRequired, requiresAuth, urgencyLevel, denialHistory
Tabelas Tasy de origem: AUTORIZACAO_CONVENIO, AUTORIZACAO_PROCEDIMENTO

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
NR_SEQ_AUTORIZACAO	NUMBER	Sim	ClaimResponse.id	authorizationId	PK da autorizacao
NR_ATENDIMENTO	NUMBER	Sim	ClaimResponse.request	encounterId	FK para atendimento
NR_SEQ_PACIENTE	NUMBER	Sim	ClaimResponse.patient	patientId	FK para paciente
CD_CONVENIO	NUMBER	Sim	ClaimResponse.insurer	payerId	Operadora
NR_GUIA_AUTORIZACAO	VARCHAR2	Nao	ClaimResponse.preAuthRef	authNumber, authorizationNumber	Numero da guia de autorizacao
IE_STATUS_AUTORIZACAO	VARCHAR2	Sim	ClaimResponse.outcome	authorizationStatus	A=Aprovada, N=Negada, P=Pendente, C=Cancelada
DT_SOLICITACAO	TIMESTAMP	Sim	ClaimResponse.created	authRequestDate	Data da solicitacao
DT_VALIDADE_AUTH	DATE	Nao	ClaimResponse.preAuthPeriod.end	authDeadline, authorizationDeadline	Validade da autorizacao
DS_MOTIVO_NEGATIVA	VARCHAR2	Nao	ClaimResponse.error[0].code	denialReason	Motivo da negativa
CD_PROCEDIMENTO_AUTH	VARCHAR2	Nao	ClaimResponse.item[0].adjudication	authorizedProcedure	Procedimento autorizado (TUSS)
QT_AUTORIZADA	NUMBER	Nao	ClaimResponse.item[0].quantity	authorizedQuantity	Quantidade autorizada
VL_AUTORIZADO	NUMBER(15,2)	Nao	ClaimResponse.extension[approvedAmount]	approvedAmount, authorizedAmount	Valor aprovado BRL
QT_DIAS_AUTORIZADOS	NUMBER	Nao	ClaimResponse.extension[authorizedDays]	authorizedDays	Dias autorizados (internacao)
CD_ESTABELECIMENTO	NUMBER	Sim	--	tenantId	Tenant

-- Tabelas: AUTORIZACAO_CONVENIO, AUTORIZACAO_PROCEDIMENTO-- Join: AUTORIZACAO_PROCEDIMENTO.NR_SEQ_AUTORIZACAO = AC.NR_SEQ_AUTORIZACAO-- Filtros: CD_ESTABELECIMENTO = :tenant-- Mapeamento status: A->complete, N->error, P->active, C->cancelled