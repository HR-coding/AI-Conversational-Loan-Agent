import os
import requests
import json
import logging
from langchain_core.tools import tool
from pydantic import BaseModel, Field, validator
from tenacity import retry, stop_after_attempt, wait_exponential
from services.pdf_service import PDFService
from services.db_service import DBService

logger = logging.getLogger(__name__)

pdf_service = PDFService()
db_service = DBService()

CRM_URL = "http://localhost:5001"
CREDIT_URL = "http://localhost:5002"
OFFER_URL = "http://localhost:5003"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")

# ================= PYDANTIC MODELS FOR VALIDATION =================
class UnderwritingInput(BaseModel):
    pan: str = Field(min_length=10, max_length=10, description="Customer PAN number")
    amount: int = Field(gt=0, le=10_000_000, description="Loan amount in rupees (max 1 crore)")
    monthly_salary: int = Field(ge=0, description="Monthly salary in rupees, 0 if unknown")
    
    @validator('amount')
    def validate_amount(cls, v):
        if v < 10000:
            raise ValueError("Minimum loan amount is ₹10,000")
        return v

class SanctionLetterInput(BaseModel):
    name: str = Field(min_length=2, description="Customer name")
    pan: str = Field(min_length=10, max_length=10, description="PAN number")
    amount: int = Field(gt=0, description="Approved loan amount")
    interest: float = Field(gt=0, lt=50, description="Interest rate percentage")

# ================= RETRY DECORATORS =================
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_api_with_retry(url: str, payload: dict, timeout: int = 5):
    """Generic API caller with retry logic"""
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

# ================= SALES TOOLS =================
@tool
def get_market_rates_tool():
    """Returns current interest rate options for different loan tenures.
    
    Returns:
        dict: Interest rates for 12-month and 24-month tenures
    """
    logger.info("Fetching market rates")
    return {
        "status": "success",
        "rates": [
            {"tenure": "12 months", "rate": "10.5%", "processing_fee": "1%"},
            {"tenure": "24 months", "rate": "11.0%", "processing_fee": "1.5%"},
            {"tenure": "36 months", "rate": "12.0%", "processing_fee": "2%"}
        ]
    }

@tool
def check_user_history_tool(name: str):
    """Checks database for previous loan applications by customer name.
    
    Args:
        name: Customer's full name
        
    Returns:
        dict: Previous loan history or indication of new customer
    """
    logger.info(f"Checking history for: {name}")
    try:
        result = db_service.check_user_history(name)
        return {
            "status": "success",
            "customer": name,
            "history": result
        }
    except Exception as e:
        logger.error(f"Error checking user history: {str(e)}")
        return {
            "status": "error",
            "message": "Unable to retrieve customer history",
            "error": str(e)
        }

# ================= KYC TOOLS =================
@tool
def verification_agent_tool(pan: str):
    """Verifies PAN number against CRM system for KYC compliance.
    
    Args:
        pan: 10-character PAN number (e.g., ABCDE1234F)
        
    Returns:
        dict: Verification status with customer details if successful
    """
    logger.info(f"Verifying PAN: {pan[:4]}****{pan[-2:]}")
    
    # Input validation
    if not pan or len(pan) != 10:
        return {
            "verified": False,
            "error": "Invalid PAN format. Must be 10 characters."
        }
    
    try:
        result = call_api_with_retry(
            f"{CRM_URL}/verify-kyc",
            {"pan": pan.upper()}
        )
        
        logger.info(f"KYC verification result: {result.get('status', 'failed')}")
        return {
            "verified": result.get("status") == "verified",
            "message": "KYC verification complete",
            "name": result.get("name", ""),
            "pan": pan.upper()
        }
        
    except requests.Timeout:
        logger.error("CRM service timeout")
        return {
            "verified": False,
            "error": "CRM service is taking too long to respond. Please try again."
        }
    except requests.RequestException as e:
        logger.error(f"CRM service error: {str(e)}")
        return {
            "verified": False,
            "error": "CRM service is currently unavailable. Please try again later."
        }
    except Exception as e:
        logger.error(f"Unexpected error in KYC verification: {str(e)}")
        return {
            "verified": False,
            "error": f"Verification failed: {str(e)}"
        }

# ================= UNDERWRITING TOOLS =================
@tool(args_schema=UnderwritingInput)
def underwriting_agent_tool(pan: str, amount: int, monthly_salary: int = 0):
    """Evaluates loan eligibility based on credit score, pre-approved limit, and salary.
    
    Decision Logic:
    - Credit score < 700: REJECTED
    - Amount ≤ pre-approved limit: APPROVED
    - Amount ≤ 2x pre-approved limit: NEED_SALARY (if not provided), then check EMI
    - Amount > 2x pre-approved limit: REJECTED
    - EMI must be ≤ 50% of monthly salary
    
    Args:
        pan: Customer PAN number (required for fetching credit data)
        amount: Requested loan amount in rupees
        monthly_salary: Monthly salary in rupees (0 if not provided yet)
        
    Returns:
        dict: Status (APPROVED/REJECTED/NEED_SALARY) with details
    """
    logger.info(f"Underwriting evaluation: PAN={pan[:4]}****, Amount={amount}, Salary={monthly_salary}")
    
    try:
        # Fetch credit score (REQUIRED)
        try:
            credit_response = call_api_with_retry(f"{CREDIT_URL}/get-score", {"pan": pan})
            credit_score = credit_response.get("credit_score", 0)
        except Exception as e:
            logger.error(f"Credit bureau error: {str(e)}")
            return {
                "status": "ERROR",
                "error": "Unable to fetch credit score. Please try again later."
            }
        
        # Fetch pre-approved limit (OPTIONAL - if fails, use salary-based approval)
        pre_approved_limit = None
        try:
            offer_response = call_api_with_retry(f"{OFFER_URL}/get-limit", {"pan": pan})
            pre_approved_limit = offer_response.get("pre_approved_limit", 0)
            logger.info(f"Credit Score: {credit_score}, Pre-approved Limit: {pre_approved_limit}")
        except Exception as e:
            logger.warning(f"Offer service error (non-fatal): {str(e)}")
            logger.info(f"Credit Score: {credit_score}, Pre-approved Limit: Not available (will use salary-based approval)")
        
        # Rule 1: Credit score must be >= 700
        if credit_score < 700:
            return {
                "status": "REJECTED",
                "reason": f"Credit score ({credit_score}) is below minimum requirement of 700",
                "credit_score": credit_score,
                "suggestion": "Please improve your credit score and reapply after 3 months"
            }
        
        # If pre-approved limit available, use it for initial checks
        if pre_approved_limit:
            # Rule 2: Amount within pre-approved limit - instant approval
            if amount <= pre_approved_limit:
                return {
                    "status": "APPROVED",
                    "amount": amount,
                    "interest_rate": 10.5,
                    "credit_score": credit_score,
                    "pre_approved_limit": pre_approved_limit,
                    "reason": "Amount within pre-approved limit"
                }
            
            # Rule 3: Amount between 1x and 2x pre-approved limit
            if amount <= (2 * pre_approved_limit):
                # Need salary information
                if monthly_salary == 0:
                    return {
                        "status": "NEED_SALARY",
                        "message": "Please provide your monthly salary to proceed with evaluation",
                        "amount": amount,
                        "credit_score": credit_score,
                        "pre_approved_limit": pre_approved_limit
                    }
        else:
            # Pre-approved limit not available - if no salary provided, ask for it
            if monthly_salary == 0:
                return {
                    "status": "NEED_SALARY",
                    "message": "Please provide your monthly salary to proceed with evaluation",
                    "amount": amount,
                    "credit_score": credit_score
                }
        
        # USER REQUIREMENT: Salary during loan duration should be at least 2x the loan amount
        # Assuming 24-month loan duration
        loan_duration_months = 24
        total_salary_over_duration = monthly_salary * loan_duration_months
        required_salary = amount * 2
        
        logger.info(f"Salary Check: Total over {loan_duration_months} months = ₹{total_salary_over_duration}, Required (2x loan) = ₹{required_salary}")
        
        if total_salary_over_duration < required_salary:
            return {
                "status": "REJECTED",
                "reason": f"Total salary over {loan_duration_months} months (₹{total_salary_over_duration:,}) is less than 2x the loan amount (₹{required_salary:,})",
                "monthly_salary": monthly_salary,
                "loan_duration_months": loan_duration_months,
                "total_salary": total_salary_over_duration,
                "required_amount": required_salary,
                "max_loan_amount": int(total_salary_over_duration / 2),
                "suggestion": f"Maximum eligible loan based on your salary: ₹{int(total_salary_over_duration / 2):,}"
            }
        
        # Calculate EMI (simple estimation: amount/24 months * 1.1 for interest)
        estimated_emi = (amount / loan_duration_months) * 1.1
        max_allowed_emi = 0.5 * monthly_salary
        
        logger.info(f"EMI Check: Estimated={estimated_emi}, Max Allowed={max_allowed_emi}")
        
        if estimated_emi <= max_allowed_emi:
            # APPROVED based on salary validation
            interest_rate = 10.5 if pre_approved_limit else 12.0  # Slightly higher rate if pre-approved limit not available
            return {
                "status": "APPROVED",
                "amount": amount,
                "interest_rate": interest_rate,
                "credit_score": credit_score,
                "monthly_emi": round(estimated_emi, 2),
                "monthly_salary": monthly_salary,
                "loan_duration_months": loan_duration_months,
                "pre_approved_limit": pre_approved_limit,
                "reason": "Salary verification successful - Meets 2x loan requirement and EMI within affordability"
            }
        else:
            return {
                "status": "REJECTED",
                "reason": f"EMI (₹{round(estimated_emi, 2)}) exceeds 50% of salary (₹{monthly_salary})",
                "estimated_emi": round(estimated_emi, 2),
                "monthly_salary": monthly_salary,
                "max_loan_amount": int(max_allowed_emi * loan_duration_months / 1.1),
                "suggestion": f"Maximum eligible amount based on EMI: ₹{int(max_allowed_emi * loan_duration_months / 1.1):,}"
            }
        
    except Exception as e:
        logger.error(f"Unexpected error in underwriting: {str(e)}")
        return {
            "status": "ERROR",
            "error": f"Underwriting evaluation failed: {str(e)}"
        }

@tool(args_schema=SanctionLetterInput)
def sanction_letter_tool(name: str, pan: str, amount: int, interest: float):
    """Generates PDF sanction letter and saves loan details to database.
    
    Args:
        name: Customer's full name
        pan: Customer's PAN number
        amount: Approved loan amount
        interest: Interest rate percentage
        
    Returns:
        dict: Download link for the sanction letter PDF
    """
    logger.info(f"Generating sanction letter for {name}, Amount: {amount}")
    
    try:
        # Generate PDF with PAN for enhanced details
        filename = pdf_service.generate(name, amount, interest, pan=pan)
        pdf_url = f"{API_BASE_URL}/static/pdfs/{filename}"
        
        # Save to database
        db_service.save_loan(name, pan, amount, pdf_url)
        
        logger.info(f"Sanction letter generated: {filename}")
        return {
            "status": "success",
            "message": "Sanction letter generated successfully",
            "download_link": pdf_url,
            "filename": filename,
            "customer_name": name,
            "loan_amount": amount,
            "interest_rate": interest
        }
        
    except Exception as e:
        logger.error(f"Error generating sanction letter: {str(e)}")
        return {
            "status": "error",
            "message": "Failed to generate sanction letter",
            "error": str(e)
        }