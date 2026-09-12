# Ресурсная смета MLOps инфраструктуры

VM: Timeweb Cloud 12 vCPU / 32GB RAM / 100GB SSD

## Базовая нагрузка (idle)

| Компонент | CPU (request) | RAM (request) | CPU (limit) | RAM (limit) | Примечание |
|---|---|---|---|---|---|
| K3s core | - | - | - | - | 0.5 vCPU / 0.75GB |
| Traefik + CoreDNS | - | - | - | - | 0.3 vCPU / 0.4GB |
| postgres | 500m | 1Gi | 1000m | 2Gi | 1 инстанс для всех БД |
| redis | 100m | 256Mi | 500m | 512Mi | Airflow backend |
| minio | 300m | 512Mi | 1000m | 1Gi | S3 хранилище |
| gitea | 200m | 512Mi | 1000m | 2Gi | Git + Actions + Registry |
| gitea-act-runner | 100m | 256Mi | 500m | 512Mi | CI/CD executor (shell:host) |
| gitea-act-runner-dind | 50m | 64Mi | 200m | 256Mi | Docker-in-Docker sidecar чарта `actions` (не используется job'ами shell:host, но чарт разворачивает его безусловно) |
| mlflow | 200m | 512Mi | 1000m | 2Gi | Tracking + Model Registry |
| airflow-webserver | 200m | 512Mi | 1000m | 2Gi | UI + API |
| airflow-scheduler | 200m | 512Mi | 1000m | 2Gi | Task scheduling |
| airflow-triggerer | 100m | 256Mi | 500m | 1Gi | Event-based triggers |
| cert-manager | 100m | 256Mi | 500m | 512Mi | TLS automation |
| serving | 200m | 512Mi | 1000m | 2Gi | FastAPI classification |
| frontend | 100m | 256Mi | 500m | 512Mi | nginx SPA |
| prometheus-operator | 50m | 64Mi | 100m | 128Mi | kube-prometheus-stack operator |
| prometheus | 300m | 512Mi | 500m | 1Gi | metrics TSDB, retention 7d |
| kube-state-metrics | 20m | 64Mi | 100m | 128Mi | k8s object metrics |
| node-exporter | 20m | 32Mi | 50m | 64Mi | DaemonSet, host metrics |
| grafana | 100m | 128Mi | 200m | 256Mi | дашборды, публичный ingress |
| **TOTAL BASELINE** | **3.44 vCPU** | **7.18GB** | **10.65 vCPU** | **19.86GB** | idle-состояние |

## Пиковые нагрузки

| Сценарий | CPU пик | RAM пик | Длительность | Примечание |
|---|---|---|---|---|
| Kaniko build (образ ~500MB) | +1.5 vCPU | +2GB | 3-5 мин | одна сборка |
| Airflow worker pod (1 DAG) | +500m | +1GB | variable | параллельно с baseline |
| Одновременно Kaniko + worker | ~5 vCPU | ~9.3GB | несколько мин | пиковая нагрузка |

## Расчёт запаса

| Метрика | Запрос (request) | Лимит (limit) | Доступно | Запас |
|---|---|---|---|---|
| CPU | 3.44 vCPU | 10.65 vCPU | 12 vCPU | 1.35 vCPU |
| RAM | 7.18GB | 19.86GB | 32GB | 12.14GB |

**Вывод**: после добавления мониторинг-стека (prometheus-grafana без
Alertmanager, только метрики — Loki/promtail исключены из скоупа, тир 2)
лимит CPU — 10.65 из 12 vCPU, запас 1.35 vCPU. Совпадение Kaniko-билда
(+1.5 vCPU) или Airflow worker'а (+500m) с пиком самого мониторинга может
привести к кратковременному throttling, не к OOM (лимиты памяти запас
держат — 12.14GB). `kubectl top nodes` во время демо не лишний, как и
раньше.

## Namespaces

- `mlops` — все приложения (Gitea, MinIO, Postgres, Redis, MLflow, Airflow, serving, frontend)
- `monitoring` — prometheus-grafana
- `argocd` — ArgoCD control plane
- `cert-manager` — Certificate Issuer и Resources для TLS
- `kube-system` — K3s системные компоненты

## Persistence

Все StatefulSet'ы и сервисы с состоянием используют `local-path` StorageClass (K3s default):

- `postgres`: 20Gi
- `redis`: 2Gi
- `minio`: 30Gi
- `gitea`: 10Gi
- `gitea-act-runner`: 1Gi (`data-runner`, чарт `actions` v0.1.2)
- `prometheus`: 5Gi
- `grafana`: 1Gi
- **Итого**: 69Gi из 100Gb SSD

## Контроль ресурсов

1. **requests** — гарантированный запас на ноде для планирования пода
2. **limits** — жёсткий потолок (OOM/Throttle при превышении)
3. **Без QoS Best Effort** — все поды с requests/limits получают QoS Guaranteed/Burstable

## SRE рекомендации

- Настроить liveness/readiness probes (сделано в values.yaml каждого компонента)
- Включить `kubectl top nodes` мониторинг перед демо
- Snapshot VM перед демо-днём в Timeweb Cloud
- Rate-limit на `api.alexshishin.ru` в Traefik (опционально)