{{/*
Expand the name of the chart.
*/}}
{{- define "maestro.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "maestro.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "maestro.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "maestro.labels" -}}
helm.sh/chart: {{ include "maestro.chart" . }}
{{ include "maestro.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: maestro
{{- end }}

{{/*
Selector labels
*/}}
{{- define "maestro.selectorLabels" -}}
app.kubernetes.io/name: {{ include "maestro.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "maestro.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "maestro.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
CIB Seven specific labels
*/}}
{{- define "maestro.cibSeven.labels" -}}
{{ include "maestro.labels" . }}
app.kubernetes.io/component: bpm-engine
{{- end }}

{{/*
CIB Seven selector labels
*/}}
{{- define "maestro.cibSeven.selectorLabels" -}}
{{ include "maestro.selectorLabels" . }}
app.kubernetes.io/component: bpm-engine
{{- end }}

{{/*
Worker labels
*/}}
{{- define "maestro.worker.labels" -}}
{{ include "maestro.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
HAPI FHIR labels
*/}}
{{- define "maestro.hapiFhir.labels" -}}
{{ include "maestro.labels" . }}
app.kubernetes.io/component: fhir-server
{{- end }}

{{/*
CDC Bridge labels
*/}}
{{- define "maestro.cdcBridge.labels" -}}
{{ include "maestro.labels" . }}
app.kubernetes.io/component: cdc-bridge
{{- end }}

{{/*
Webhook Receiver labels
*/}}
{{- define "maestro.webhookReceiver.labels" -}}
{{ include "maestro.labels" . }}
app.kubernetes.io/component: webhook-receiver
{{- end }}

{{/*
Generate database URL for CIB Seven
*/}}
{{- define "maestro.cibSeven.databaseUrl" -}}
jdbc:postgresql://{{ .Release.Name }}-postgresql:5432/{{ .Values.postgresql.auth.database }}
{{- end }}

{{/*
Generate FHIR database URL
*/}}
{{- define "maestro.hapiFhir.databaseUrl" -}}
jdbc:postgresql://{{ .Release.Name }}-postgresql:5432/fhir
{{- end }}

{{/*
Generate Kafka bootstrap servers
*/}}
{{- define "maestro.kafkaBootstrapServers" -}}
{{ .Release.Name }}-kafka:9092
{{- end }}

{{/*
Generate Redis URL
*/}}
{{- define "maestro.redisUrl" -}}
redis://{{ .Release.Name }}-redis-master:6379
{{- end }}

{{/*
Generate Keycloak URL
*/}}
{{- define "maestro.keycloakUrl" -}}
http://{{ .Release.Name }}-keycloak:8080
{{- end }}

{{/*
Generate CIB Seven internal URL
*/}}
{{- define "maestro.cibSevenUrl" -}}
http://{{ include "maestro.fullname" . }}-cib-seven:8080/engine-rest
{{- end }}

{{/*
Generate FHIR internal URL
*/}}
{{- define "maestro.fhirUrl" -}}
http://{{ include "maestro.fullname" . }}-hapi-fhir:8080/fhir
{{- end }}

{{/*
Multi-tenant configuration as JSON
*/}}
{{- define "maestro.tenantsJson" -}}
{{- .Values.global.tenants | toJson }}
{{- end }}
