python -m celery -A server_celery.app worker --pool=solo --loglevel=info

python -m celery -A server_celery.app beat --loglevel=info