V04 - VW_FHIR_PROCEDURE
Recurso FHIR: Procedure Descricao: Procedimentos realizados por atendimento com codigo TUSS. Base para producao, codificacao, faturamento e precificacao.
Processos que consomem:
SP-RC-001 (check_eligibility -> procedureCode)
SP-RC-002 (check_authorization, request_authorization, validate_procedure -> procedureCode, procedureCodes)
SP-RC-003 (capture_procedure, enrich_procedure -> tussCodes, calculate_quantity)
SP-RC-004 (assign_prices -> procedureCodes, validate_compatibility, calculate_value, capture_charges)
SP-RC-005 (suggest_tuss, check_compatibility, detect_fraud)
SP-RC-006 (validate_claim -> procedureCodes, calculate_charges, procedure_pricing -> procedureCode, complexity, urgency, duration, equipment)
Variaveis BPMN alimentadas: procedureCode, procedureCodes, tussCodes, procedureDescription, procedureStatus, performedDate, performedEnd, estimatedDuration (calculado), quantity, performerPractitioner, bodySite, authorizationId, complexity, procedureUrgency, equipmentUsed
Tabelas Tasy de origem: PROCEDIMENTO_PACIENTE, PROCEDIMENTO

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
NR_SEQ_PROCEDIMENTO	NUMBER	Sim	Procedure.id	procedureId	PK do procedimento realizado
NR_ATENDIMENTO	NUMBER	Sim	Procedure.encounter	encounterId	FK para atendimento
NR_SEQ_PACIENTE	NUMBER	Sim	Procedure.subject	patientId	FK para paciente
CD_PROCEDIMENTO	VARCHAR2(8)	Sim	Procedure.code.coding[0].code	procedureCode, tussCodes	Codigo TUSS (8 digitos)
DS_PROCEDIMENTO	VARCHAR2	Nao	Procedure.code.coding[0].display	procedureDescription	Descricao do procedimento
IE_STATUS_PROC	VARCHAR2	Sim	Procedure.status	procedureStatus	R=Realizado, C=Cancelado, P=Pendente
DT_PROCEDIMENTO	TIMESTAMP	Sim	Procedure.performedDateTime	performedDate	Data/hora da realizacao
DT_FIM_PROCEDIMENTO	TIMESTAMP	Nao	Procedure.performedPeriod.end	performedEnd	Fim (para calculo de duracao)
QT_PROCEDIMENTO	NUMBER	Sim	Procedure.extension[quantity]	quantity	Quantidade realizada
CD_MEDICO_EXECUTOR	NUMBER	Nao	Procedure.performer[0].actor	performerPractitioner	Medico executor
CD_REGIAO_ANATOMICA	VARCHAR2	Nao	Procedure.bodySite	bodySite	Regiao anatomica
NR_SEQ_AUTORIZACAO	NUMBER	Nao	Procedure.extension[authorization]	authorizationId	FK para autorizacao
CD_ESTABELECIMENTO	NUMBER	Sim	--	tenantId	Tenant

-- Tabelas: PROCEDIMENTO_PACIENTE, PROCEDIMENTO (tabela de dominio)-- Join: PROCEDIMENTO.CD_PROCEDIMENTO = PP.CD_PROCEDIMENTO-- Filtros: CD_ESTABELECIMENTO = :tenant, NR_ATENDIMENTO = :encounter-- Coding system: http://www.ans.gov.br/tuss-- Nota: DT_FIM - DT_PROCEDIMENTO = duracao (estimatedDuration para anestesia, UTI)
Alerta DEPARA 2025: Campo "STATUS" sempre vazio no Tasy para PRESCR_PROCEDIMENTO. Campo "code" (codigo do procedimento) marcado como "Nao" disponivel diretamente. Verificar se PROCEDIMENTO_PACIENTE tem o campo correto.