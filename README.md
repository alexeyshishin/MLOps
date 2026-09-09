# MLOps

## Установка K3s на VM

```bash
ssh <user>@<VM_IP>
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.36.4+k3s1" sh -
k3s kubectl get nodes
```

## Установка Kubeconfig на свою машину

```bash
ssh root@200.169.183.169 "cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/mlops.yaml
sed -i '' "s/127.0.0.1/200.169.183.169/; s/default/mlops/g" ~/.kube/mlops.yaml
chmod 600 ~/.kube/mlops.yaml
export KUBECONFIG=~/.kube/mlops.yaml
kubectl get nodes
```

## Раскатка кластера

Источник манифестов для ArgoCD — GitHub (`https://github.com/alexeyshishin/MLOps.git`), постоянно, без миграции на свой Gitea. Gitea в кластере поднимается только под Container Registry и Act Runner (CI), GitOps-источником не является — иначе курица-яйцо (ArgoCD не может стянуть манифесты из Gitea, которую сам же должен развернуть).

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
cp argocd/secrets/argocd-admin-secret.template.yaml argocd/secrets/argocd-admin-secret.yaml
htpasswd -nbBC 10 "" "<пароль admin>" | tr -d ':\n' | sed 's/^\$2y/\$2a/'
htpasswd -nbBC 10 "" "<пароль readonly>" | tr -d ':\n' | sed 's/^\$2y/\$2a/'
date -u +"%Y-%m-%dT%H:%M:%SZ"
# вписать хэши и timestamp в argocd/secrets/argocd-admin-secret.yaml (НЕ в template — тот в git, только placeholder)
kubectl apply -f argocd/secrets/argocd-admin-secret.yaml
```

```bash
grep -rl "https://github.com/alexeyshishin/MLOps.git" . | xargs sed -i '' 's#https://github.com/alexeyshishin/MLOps.git#https://github.com/alexeyshishin/MLOps.git#g'
git add -A
git commit -m "chore: set argocd source repo url"
git push
```

```bash
kubectl apply -f argocd/bootstrap/root.yaml
kubectl -n argocd get applications -w
```

Дождаться, что контроллер живой — kubeseal без него не отработает:

```bash
kubectl -n kube-system get pods -w   # sealed-secrets-controller -> Running
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
# вписать REPLACE_WITH_* в каждом файле (template-* НЕ трогать — они в git, только placeholder)
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

Запушить sealed-секреты — wave 1 (`secrets`) тянет их из `manual/secrets/dev/sealed` на GitHub, локальный `kubectl apply` тут не поможет:

```bash
git add manual/secrets/dev/sealed
git commit -m "chore(secrets): seal dev secrets"
git push
kubectl -n argocd get applications -w
```

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

```bash
kubectl get certificate -n cert-manager
```

Sync-wave 2 (`ingress-tls`) кладёт только `Certificate`-ресурсы — сам `ClusterIssuer` (`letsencrypt-http01`, ACME HTTP01 через traefik) лежит отдельно, `ingress/main-tls/issuer`, подключён к `ingress/main-tls/dev` вторым base. Без него все `Certificate` висят `False: Issuing certificate as Secret does not exist` бесконечно — `ClusterIssuer` не создаётся сам, `kubectl get clusterissuer` пустой.

Настроить Gitea: `https://git.alexshishin.ru`, логин из `manual/secrets/dev/gitea.yaml`, включить Container Registry, создать репозиторий (для CI/Registry, не для GitOps-манифестов), запушить туда содержимое `MLOps/`.

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

## Dry-run проверка

```bash
python3 scripts/dry-run-cluster.py
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
| `minio-secret` | mlops | `rootUser`, `rootPassword` |
| `gitea-secret` | mlops | `username`, `password` |
| `gitea-act-runner-secret` | mlops | `token` |
| `mlflow-basic-auth-secret` | mlops | `username`, `password` |
| `airflow-postgres-secret` | mlops | `connection` |
| `airflow-redis-secret` | mlops | `connection` |
| `airflow-webserver-secret` | mlops | `webserver-secret-key` |
| `argocd-secret` | argocd | `admin.password`, `admin.passwordMtime`, `accounts.readonly.password`, `accounts.readonly.passwordMtime` |

Postgres/redis пароли в `airflow.yaml` должны совпадать с `postgres.yaml`/`redis.yaml`.
