{{/*
Expand the name of the chart.
*/}}
{{- define "tsushin.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "tsushin.fullname" -}}
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
{{- define "tsushin.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "tsushin.labels" -}}
helm.sh/chart: {{ include "tsushin.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tsushin
{{- end }}

{{/*
Backend labels
*/}}
{{- define "tsushin.backend.labels" -}}
{{ include "tsushin.labels" . }}
app.kubernetes.io/name: {{ include "tsushin.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
app.kubernetes.io/version: {{ .Values.backend.image.tag | default .Chart.AppVersion | quote }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "tsushin.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tsushin.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "tsushin.frontend.labels" -}}
{{ include "tsushin.labels" . }}
app.kubernetes.io/name: {{ include "tsushin.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
app.kubernetes.io/version: {{ .Values.frontend.image.tag | default .Chart.AppVersion | quote }}
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "tsushin.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tsushin.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend service account name
*/}}
{{- define "tsushin.backend.serviceAccountName" -}}
{{ include "tsushin.fullname" . }}-backend
{{- end }}

{{/*
Frontend service account name
*/}}
{{- define "tsushin.frontend.serviceAccountName" -}}
{{ include "tsushin.fullname" . }}-frontend
{{- end }}

{{/*
Secret name — use external if configured, otherwise chart-managed
*/}}
{{- define "tsushin.secretName" -}}
{{- if .Values.secrets.external }}
{{- .Values.secrets.externalSecretName }}
{{- else }}
{{- include "tsushin.fullname" . }}-secrets
{{- end }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "tsushin.configMapName" -}}
{{ include "tsushin.fullname" . }}-config
{{- end }}

{{/*
Namespace
*/}}
{{- define "tsushin.namespace" -}}
{{- default "tsushin" .Release.Namespace }}
{{- end }}
