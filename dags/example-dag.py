from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator

default_args = {
    'owner': 'mlops',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'intent-classification-pipeline',
    default_args=default_args,
    description='Intent classification model training and evaluation',
    schedule_interval='@daily',
    start_date=datetime(2026, 9, 11),
    catchup=False,
)

def log_start():
    print('Pipeline started')

def log_end():
    print('Pipeline completed')

start = PythonOperator(
    task_id='start',
    python_callable=log_start,
    dag=dag,
)

train_task = KubernetesPodOperator(
    task_id='train',
    image='git.alexshishin.ru/training:latest',
    namespace='mlops',
    in_cluster=True,
    service_account_name='default',
    is_delete_operator_pod=True,
    dag=dag,
    get_logs=True,
)

eval_task = KubernetesPodOperator(
    task_id='evaluate',
    image='git.alexshishin.ru/training:latest',
    namespace='mlops',
    in_cluster=True,
    service_account_name='default',
    is_delete_operator_pod=True,
    dag=dag,
    get_logs=True,
)

end = PythonOperator(
    task_id='end',
    python_callable=log_end,
    dag=dag,
)

start >> train_task >> eval_task >> end
