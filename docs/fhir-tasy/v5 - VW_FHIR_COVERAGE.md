V05 - VW_FHIR_COVERAGE
Recurso FHIR: Coverage Descricao: Dados de convenio/plano do paciente. Necessario para verificacao de elegibilidade, autorizacao, regras de contrato e faturamento.
Processos que consomem:
SP-RC-001 (verify_insurance -> cardNumber, check_eligibility -> insuranceData)
SP-RC-002 (check_authorization -> payerId, request_authorization -> payerId)
SP-RC-006 (validate_claim -> coverageFhirId, apply_contract_rules -> contractId, generate_tiss -> coverageFhirId)
SP-RC-014 (verify_coverage, insurance_request)
SP-RC-017 (patient budget -> insurancePlan)
Variaveis BPMN alimentadas: payerId, payerName, planCode, cardNumber, coverageEndDate, coverageType, isActive, contractId, coverageFhirId, insuranceData
Tabelas Tasy de origem: CONVENIO_PACIENTE, CONVENIO, PLANO_CONVENIO

Coluna Tasy	Tipo Oracle	Obrig.	FHIR Path	Variavel BPMN	Descricao
NR_SEQ_CONVENIO_PACIENTE	NUMBER	Sim	Coverage.id	coverageFhirId	PK do vinculo paciente x convenio
NR_SEQ_PACIENTE	NUMBER	Sim	Coverage.beneficiary	patientId	FK para paciente
CD_CONVENIO	NUMBER	Sim	Coverage.payor	payerId	FK para operadora
NM_CONVENIO	VARCHAR2	Nao	Coverage.payor.display	payerName	Nome do convenio
CD_PLANO	VARCHAR2	Nao	Coverage.class[plan]	planCode	Codigo do plano
NR_CARTEIRA	VARCHAR2	Sim	Coverage.identifier	cardNumber	Numero da carteirinha
DT_VALIDADE	DATE	Nao	Coverage.period.end	coverageEndDate	Validade da carteirinha
IE_TIPO_COBERTURA	VARCHAR2	Nao	Coverage.type	coverageType	A=Ambulatorial, H=Hospitalar, AH=Ambos
IE_ATIVO	VARCHAR2(1)	Sim	Coverage.status	isActive	S=active, N=cancelled
CD_CONTRATO	NUMBER	Nao	Coverage.extension[contract]	contractId	FK para contrato (tabela de preco)
CD_ESTABELECIMENTO	NUMBER	Sim	--	tenantId	Tenant

-- Tabelas: CONVENIO_PACIENTE, CONVENIO, PLANO_CONVENIO-- Join: CONVENIO.CD_CONVENIO = CP.CD_CONVENIO-- Filtros: CD_ESTABELECIMENTO = :tenant, IE_ATIVO = 'S'

select



ap.cd_pessoa_fisica,

ac.cd_convenio,

obter_desc_convenio(ac.cd_convenio) ds_convenio,

ac.cd_plano_convenio,

ac.cd_usuario_convenio,

ac.dt_validade_carteira,

ac.cd_tipo_acomodacao,

(select ds_tipo_acomodacao from tipo_acomodacao where cd_tipo_acomodacao = ac.cd_tipo_acomodacao) ds_acomodacao,

'' ie_ativo,

'' cd_contrato,

ap.cd_estabelecimento

from atendimento_paciente ap,

atend_categoria_convenio ac

where ap.nr_atendimento = ac.nr_atendimento

and ap.dt_cancelamento is not null