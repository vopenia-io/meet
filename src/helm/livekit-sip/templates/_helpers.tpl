{{- define "livekit-sip.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "livekit-sip.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "livekit-sip.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "livekit-sip.labels" -}}
app.kubernetes.io/name: {{ include "livekit-sip.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "livekit-sip.selectorLabels" -}}
app.kubernetes.io/name: {{ include "livekit-sip.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
