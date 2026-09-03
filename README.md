# MLOps

```bash
kubectl apply -k namespaces/dev
```

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd argo/argo-cd -n argocd -f argocd/values-dev.yaml
kubectl -n argocd get pods -w
```

```bash
htpasswd -nbBC 10 "" "<пароль>" | tr -d ':\n' | sed 's/^\$2y/\$2a/'
# вписать хэш в argocd/secrets/argocd-admin-secret.yaml
kubectl apply -f argocd/secrets/argocd-admin-secret.yaml
```

```bash
cd manual/secrets/dev
cp template-postgres.yaml postgres.yaml
cp template-redis.yaml redis.yaml
cp template-minio.yaml minio.yaml
cp template-gitea.yaml gitea.yaml
cp template-gitea-act-runner.yaml gitea-act-runner.yaml
cp template-mlflow.yaml mlflow.yaml
cp template-airflow.yaml airflow.yaml
# вписать REPLACE_WITH_* в каждом файле
openssl rand -hex 32   # для airflow-webserver-secret.webserver-secret-key
```

```bash
brew install kubeseal   # версия должна совпадать с контроллером: 0.39.1

for f in postgres redis minio gitea gitea-act-runner mlflow airflow; do
  kubeseal --format=yaml \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=kube-system \
    < "$f.yaml" > "sealed/$f.yaml"
  rm "$f.yaml"
done
cd -
```

```bash
grep -rl "GIT_REPO_URL_PLACEHOLDER" . | xargs sed -i '' 's#GIT_REPO_URL_PLACEHOLDER#https://git.alexshishin.ru/<org>/mlops.git#g'
```

```bash
kubectl apply -f argocd/bootstrap/root.yaml
kubectl -n argocd get applications -w
```

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

```bash
kubectl get certificate -n cert-manager
```

Настроить Gitea: `https://git.alexshishin.ru`, логин из `manual/secrets/dev/gitea.yaml`, включить Container Registry, создать репозиторий, запушить туда содержимое `MLOps/`.

Зарегистрировать Act Runner (Site Administration → Actions → Runners → токен):

```bash
cd manual/secrets/dev
cp template-gitea-act-runner.yaml gitea-act-runner.yaml
# вписать токен
kubeseal --format=yaml \
  --controller-name=sealed-secrets-controller \
  --controller-namespace=kube-system \
  < gitea-act-runner.yaml > sealed/gitea-act-runner.yaml
rm gitea-act-runner.yaml
cd -
git add manual/secrets/dev/sealed/gitea-act-runner.yaml
git commit -m "chore(secrets): reseal gitea act runner token"
git push
```

## Проверка манифестов локально

```bash
kustomize build namespaces/dev
kustomize build argocd/overlays/dev
kustomize build manual/secrets/dev/sealed
kustomize build ingress/main/dev
kustomize build ingress/main-tls/dev
kustomize build apps/platform/serving/dev
kustomize build apps/platform/frontend/dev
```

## Sync-wave

| Wave | Компоненты |
|---|---|
| 0 | sealed-secrets-controller, cert-manager |
| 1 | secrets |
| 2 | ingress-tls, postgres, redis, minio |
| 3 | gitea |
| 4 | gitea-act-runner |
| 5 | mlflow, airflow |
| 6 | serving, frontend |
| 7 | ingress-main |

## Секреты

| Секрет | Namespace | Ключи |
|---|---|---|
| `postgres-secret` | mlops | `postgres-password` |
| `redis-secret` | mlops | `redis-password` |
| `minio-secret` | mlops | `root-user`, `root-password` |
| `gitea-secret` | mlops | `username`, `password` |
| `gitea-act-runner-secret` | mlops | `token` |
| `mlflow-basic-auth-secret` | mlops | `username`, `password` |
| `airflow-postgres-secret` | mlops | `connection` |
| `airflow-redis-secret` | mlops | `connection` |
| `airflow-webserver-secret` | mlops | `webserver-secret-key` |
| `argocd-secret` | argocd | `admin.password`, `admin.passwordMtime` |

Postgres/redis пароли в `airflow.yaml` должны совпадать с `postgres.yaml`/`redis.yaml`.
