orchestrator: python backend/setup_database.py && gunicorn --bind 0.0.0.0:$PORT --chdir backend/orchestrator app:app
crm_service: python backend/mock_services/crm.py
credit_service: python backend/mock_services/credit_bureau.py
offer_service: python backend/mock_services/offer_mart.py