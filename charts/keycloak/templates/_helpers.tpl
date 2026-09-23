{{- define "lantern-keycloak.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: lantern-platform
{{- end }}

