# 1. The "Brain" (Now uses Gunicorn for Production Binding)
# We change directory (--chdir) to backend/orchestrator so imports work correctly
orchestrator: python backend/setup_database.py && gunicorn --bind 0.0.0.0:$PORT --chdir backend/orchestrator app:app

# 2. The "Bank" Mocks (These stay the same)
crm_service: python backend/mock_services/crm.py
credit_service: python backend/mock_services/credit_bureau.py
offer_service: python backend/mock_services/offer_mart.py