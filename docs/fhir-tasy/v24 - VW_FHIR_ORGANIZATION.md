V24 - VW_FHIR_ORGANIZATION
Recurso FHIR: Organization Descricao: Operadoras/convenios (payers). Necessario para identificar operadora em todos os fluxos de billing e collection.
Processos que consomem: Todos os fluxos RC (referenciado via payerId)
Variaveis BPMN alimentadas: payerId, payerName, payerCnpj, payerAnsCode
Tabelas Tasy de origem: CONVENIO

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
CD_CONVENIO	NUMBER	Sim	Organization.id	payerId	PK da operadora
NM_CONVENIO	VARCHAR2	Sim	Organization.name	payerName	Nome da operadora
NR_CNPJ	VARCHAR2	Nao	Organization.identifier[cnpj]	payerCnpj	CNPJ
NR_ANS	VARCHAR2	Nao	Organization.identifier[ans]	payerAnsCode	Registro ANS
IE_ATIVO	VARCHAR2(1)	Nao	Organization.active	payerActive	S=true, N=false

-- Tabelas: CONVENIO-- Sync: Polling diario (raramente muda)