# Ресурсная смета MLOps инфраструктуры

VM: Timeweb Cloud 8 vCPU / 24GB RAM / 100GB SSD

## Базовая нагрузка (idle)

| Компонент | CPU (request) | RAM (request) | CPU (limit) | RAM (limit) | Примечание |
|---|---|---|---|---|---|
| K3s core | - | - | - | - | 0.5 vCPU / 0.75GB |
| Traefik + CoreDNS | - | - | - | - | 0.3 vCPU / 0.4GB |
| postgres | 500m | 1Gi | 1000m | 2Gi | 1 инстанс для всех БД |
| redis | 100m | 256Mi | 500m | 512Mi | Airflow backend |
| minio | 300m | 512Mi | 1000m | 1Gi | S3 хранилище |
| gitea | 200m | 512Mi | 1000m | 2Gi | Git + Actions + Registry |
| gitea-act-runner | 100m | 256Mi | 1000m | 2Gi | CI/CD executor (shell) |
| mlflow | 200m | 512Mi | 1000m | 2Gi | Tracking + Model Registry |
| airflow-webserver | 200m | 512Mi | 1000m | 2Gi | UI + API |
| airflow-scheduler | 200m | 512Mi | 1000m | 2Gi | Task scheduling |
| airflow-triggerer | 100m | 256Mi | 500m | 1Gi | Event-based triggers |
| cert-manager | 100m | 256Mi | 500m | 512Mi | TLS automation |
| serving | 200m | 512Mi | 1000m | 2Gi | FastAPI classification |
| frontend | 100m | 256Mi | 500m | 512Mi | nginx SPA |
| **TOTAL BASELINE** | **2.9 vCPU** | **6.3GB** | **10 vCPU** | **19.5GB** | idle-состояние |

## Пиковые нагрузки

| Сценарий | CPU пик | RAM пик | Длительность | Примечание |
|---|---|---|---|---|
| Kaniko build (образ ~500MB) | +1.5 vCPU | +2GB | 3-5 мин | одна сборка |
| Airflow worker pod (1 DAG) | +500m | +1GB | variable | параллельно с baseline |
| Одновременно Kaniko + worker | ~5 vCPU | ~9.3GB | несколько мин | пиковая нагрузка |

## Расчёт запаса

| Метрика | Запрос (request) | Лимит (limit) | Доступно | Запас |
|---|---|---|---|---|
| CPU | 2.9 vCPU | 10 vCPU | 8 vCPU | 5.1 vCPU |
| RAM | 6.3GB | 19.5GB | 24GB | 4.5GB |

**Вывод**: базовая конфигурация укладывается в 8 vCPU / 24GB. Запас ~5 vCPU / ~4.5GB позволяет выдержать пики Kaniko и Airflow без OOM-киллов при нормальных условиях. Риск OOM остаётся при совпадении максимальной нагрузки (Kaniko + полный DAG воркер одновременно) — рекомендуется мониторинг `kubectl top nodes` во время демо.

## Namespaces

- `mlops` — все приложения (Gitea, MinIO, Postgres, Redis, MLflow, Airflow, serving, frontend)
- `argocd` — ArgoCD control plane
- `cert-manager` — Certificate Issuer и Resources для TLS
- `kube-system` — K3s системные компоненты

## Persistence

Все StatefulSet'ы и сервисы с состоянием используют `local-path` StorageClass (K3s default):

- `postgres`: 20Gi
- `redis`: 2Gi
- `minio`: 30Gi
- `gitea`: 10Gi
- **Итого**: 62Gi из 100Gb SSD

## Контроль ресурсов

1. **requests** — гарантированный запас на ноде для планирования пода
2. **limits** — жёсткий потолок (OOM/Throttle при превышении)
3. **Без QoS Best Effort** — все поды с requests/limits получают QoS Guaranteed/Burstable

## SRE рекомендации

- Настроить liveness/readiness probes (сделано в values.yaml каждого компонента)
- Включить `kubectl top nodes` мониторинг перед демо
- Snapshot VM перед демо-днём в Timeweb Cloud
- Rate-limit на `api.alexshishin.ru` в Traefik (опционально)