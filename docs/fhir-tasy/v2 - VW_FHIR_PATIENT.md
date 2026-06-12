V02 - VW_FHIR_PATIENT
Recurso FHIR: Patient Descricao: Dados demograficos do paciente. Necessario para identificacao, calculo de complexidade (idade, genero), comunicacao (WhatsApp) e TISS.
Processos que consomem:
SP-RC-001 (verify_insurance, check_eligibility, schedule_appointment)
SP-RC-002 (request_authorization - patientId, patientAge)
SP-RC-003 (capture_procedure)
SP-RC-005 (complexity via patientAge)
SP-RC-006 (generate_tiss - patientFhirId, procedure_pricing - patientAge)
SP-RC-013 (generate_collection_letter, send_whatsapp_reminder)
SP-RC-014 (patient self-service)
Variaveis BPMN alimentadas: patientId, patientFhirId, patientName, patientAge (calculado de birthDate), gender, cpf, cardNumber
Tabelas Tasy de origem: PACIENTE, PESSOA_FISICA, COMPL_PESSOA_FISICA

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
NR_SEQ_PACIENTE	NUMBER	Sim	Patient.id	patientId	ID do paciente (PK)
NM_PACIENTE	VARCHAR2	Sim	Patient.name[0].text	patientName	Nome completo
DT_NASCIMENTO	DATE	Sim	Patient.birthDate	birthDate -> patientAge	Data de nascimento
IE_SEXO	VARCHAR2(1)	Sim	Patient.gender	gender	M=male, F=female
NR_CPF	VARCHAR2	Sim	Patient.identifier[cpf]	cpf	CPF do paciente
NR_CARTEIRA_CONV	VARCHAR2	Nao	Patient.identifier[insurance]	cardNumber	Numero da carteirinha do convenio
NR_TELEFONE	VARCHAR2	Nao	Patient.telecom[phone]	phoneNumber	Telefone principal
NR_CELULAR	VARCHAR2	Nao	Patient.telecom[mobile]	whatsappNumber	Celular (usado para WhatsApp)
DS_EMAIL	VARCHAR2	Nao	Patient.telecom[email]	email	Email
CD_ESTABELECIMENTO	NUMBER	Sim	Patient.managingOrganization	tenantId	Tenant

-- Tabelas: PACIENTE, PESSOA_FISICA-- Filtros: CD_ESTABELECIMENTO = :tenant-- Sync: CDC ou polling diario (dados demograficos mudam raramente)-- NR_CELULAR deve estar em formato E.164 (+55...)
Alerta DEPARA 2025: Campos codigo_raca (NR_SEQ_COR_PELE) e codigo_etnia (CD_NACIONALIDADE) marcados como "Nao" disponiveis no Tasy. Verificar com consultores se houve atualizacao.