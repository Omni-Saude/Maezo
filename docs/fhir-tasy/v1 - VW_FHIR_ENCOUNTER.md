V01 - VW_FHIR_ENCOUNTER
Recurso FHIR: Encounter Descricao: Atendimentos do paciente (internacao, ambulatorio, urgencia). Fonte primaria para iniciar o fluxo de Revenue Cycle.
Processos que consomem:
SP-RC-000 (Orchestrator - trigger CDC)
SP-RC-003 (Clinical Service - capture_procedure, enrich_procedure, validate_clinical_data)
SP-RC-004 (Production - record_production, capture_charges)
SP-RC-005 (Coding - extract_clinical_data)
SP-RC-006 (Billing - validate_claim, generate_tiss)
SP-RC-007 (Denial - analyze_reason)
SP-RC-008 (Collection - identify_overdue)
Variaveis BPMN alimentadas: encounterId, encounterFhirId, encounterType, admissionDate, dischargeDate, encounterStatus, payerId, practitionerId, departmentCode, patientLocation, dischargeReason
Tabelas Tasy de origem: ATENDIMENTO_PACIENTE, TIPO_ATENDIMENTO, SETOR_ATENDIMENTO

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
NR_ATENDIMENTO	NUMBER	Sim	Encounter.id	encounterId	Numero do atendimento (PK)
CD_ESTABELECIMENTO	NUMBER	Sim	Encounter.serviceProvider	tenantId	Codigo do hospital/unidade (tenant)
NR_SEQ_PACIENTE	NUMBER	Sim	Encounter.subject	patientId	FK para paciente
CD_TIPO_ATENDIMENTO	VARCHAR2	Sim	Encounter.class	encounterType	Tipo: I=Internacao, A=Ambulatorial, U=Urgencia
DT_ENTRADA	TIMESTAMP	Sim	Encounter.period.start	admissionDate	Data/hora de entrada
DT_ALTA	TIMESTAMP	Nao	Encounter.period.end	dischargeDate	Data/hora de alta (NULL se em andamento)
IE_STATUS_ATEND	VARCHAR2	Sim	Encounter.status	encounterStatus	Status: A=Aberto, F=Fechado, C=Cancelado
NR_SEQ_CONVENIO	NUMBER	Nao	Encounter.extension[coverage]	payerId	FK para convenio
CD_MEDICO_RESP	NUMBER	Nao	Encounter.participant[].individual	practitionerId	Medico responsavel
CD_SETOR_ATENDIMENTO	NUMBER	Nao	Encounter.location	departmentCode, patientLocation	Setor/unidade de atendimento
CD_MOTIVO_ALTA	VARCHAR2	Nao	Encounter.hospitalization.dischargeDisposition	dischargeReason	Motivo da alta

-- SQL de referencia:-- Tabelas: ATENDIMENTO_PACIENTE, TIPO_ATENDIMENTO, SETOR_ATENDIMENTO-- Filtros: CD_ESTABELECIMENTO = :tenant, DT_ENTRADA >= :sync_from-- Sync: CDC (trigger on INSERT/UPDATE) ou polling a cada 5 min
Mapeamento de codigos:
CD_TIPO_ATENDIMENTO: I -> IMP (inpatient), A -> AMB (ambulatory), U -> EMER (emergency), D -> HH (home health)
IE_STATUS_ATEND: A -> in-progress, F -> finished, C -> cancelled