{{/*
Expand the name of the chart.
*/}}
{{- define "app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "app.fullname" -}}
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
{{- define "app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "app.labels" -}}
helm.sh/chart: {{ include "app.chart" . }}
{{ include "app.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "app.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "app.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference.
*/}}
{{- define "app.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Common environment variables (DS__*) sourced from values.yaml.
Maps directly to app/settings.py.
*/}}
{{- define "app.commonEnv" }}
- name: DS__NODE_ID
  value: "{{ .Values.contractGenerator.nodeId }}"
- name: DS__SIGNING_KEY_PATH
  value: "{{ .Values.contractGenerator.signingKeyPath }}"
- name: DS__SIGNING_KEY_ID
  value: "{{ .Values.contractGenerator.signingKeyId }}"
- name: DS__CLEARING_HOUSE_URL
  value: "{{ .Values.contractGenerator.clearingHouseUrl }}"
- name: DS__DEFAULT_TTL_SECONDS
  value: "{{ .Values.contractGenerator.defaultTtlSeconds }}"
- name: DS__MAX_ITEMS_PER_CONTRACT
  value: "{{ .Values.contractGenerator.maxItemsPerContract }}"
- name: DS__ENVIRONMENT
  value: "{{ .Values.contractGenerator.environment }}"
- name: DS__LOG_LEVEL
  value: "{{ .Values.contractGenerator.logLevel }}"
{{- end }}
