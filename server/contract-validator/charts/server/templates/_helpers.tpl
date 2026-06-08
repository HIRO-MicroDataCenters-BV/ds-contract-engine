{{- define "app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

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

{{- define "app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "app.labels" -}}
helm.sh/chart: {{ include "app.chart" . }}
{{ include "app.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "app.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "app.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "app.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "app.commonEnv" }}
- name: DS__NODE_ID
  value: "{{ .Values.contractValidator.nodeId }}"
- name: DS__CLEARING_HOUSE_URL
  value: "{{ .Values.contractValidator.clearingHouseUrl }}"
- name: DS__JWKS_BASE_URL_TEMPLATE
  value: "{{ .Values.contractValidator.jwksBaseUrlTemplate }}"
- name: DS__LEEWAY_SECONDS
  value: "{{ .Values.contractValidator.leewaySeconds }}"
- name: DS__JWKS_CACHE_TTL_SECONDS
  value: "{{ .Values.contractValidator.jwksCacheTtlSeconds }}"
- name: DS__HTTP_TIMEOUT_SECONDS
  value: "{{ .Values.contractValidator.httpTimeoutSeconds }}"
- name: DS__ENVIRONMENT
  value: "{{ .Values.contractValidator.environment }}"
- name: DS__LOG_LEVEL
  value: "{{ .Values.contractValidator.logLevel }}"
{{- end }}
