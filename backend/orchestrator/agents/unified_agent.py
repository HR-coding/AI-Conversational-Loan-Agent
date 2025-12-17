"""
Unified Single-Agent Loan Processing System
Handles sales, KYC, underwriting, and sanction letter generation in one flow
"""
import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, TypedDict, Annotated

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AnyMessage

from agents.tools import (
    get_market_rates_tool,
    check_user_history_tool,
    verification_agent_tool,
    underwriting_agent_tool,
    sanction_letter_tool
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment
# Try multiple locations (development and production)
env_locations = [
    Path(__file__).parent.parent.parent.parent / "backend" / ".env",  # From agents/
    Path.cwd() / ".env",  # From current working directory
    Path.cwd() / "backend" / ".env",  # From root
]

env_loaded = False
for env_path in env_locations:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        logger.info(f"OPENAI_API_KEY loaded from: {env_path}")
        env_loaded = True
        break

if not env_loaded:
    logger.warning(f"No .env file found in standard locations. Using environment variables.")

# Initialize LLM
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    api_key=os.getenv("OPENAI_API_KEY"),
    streaming=True
)

# ================= STATE DEFINITION =================
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    customer_name: Optional[str]
    pan_number: Optional[str]
    phone_number: Optional[str]
    loan_amount: Optional[int]
    requested_tenure: Optional[str]
    monthly_salary: Optional[int]
    kyc_verified: bool
    credit_score: Optional[int]
    pre_approved_limit: Optional[int]
    underwriting_status: str
    approved_interest_rate: Optional[float]
    sanction_letter_url: Optional[str]

# ================= HELPER FUNCTIONS =================
def extract_loan_amount(text: str) -> Optional[int]:
    """Extract loan amount from text"""
    text = text.lower()
    lakh_match = re.search(r'(\d+\.?\d*)\s*(?:lakh|lac)', text)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100000)
    thousand_match = re.search(r'(\d+\.?\d*)\s*thousand', text)
    if thousand_match:
        return int(float(thousand_match.group(1)) * 1000)
    rupee_match = re.search(r'[₹rs]\s*(\d+(?:,\d+)*)', text)
    if rupee_match:
        return int(rupee_match.group(1).replace(',', ''))
    number_match = re.search(r'\b(\d{5,})\b', text)
    if number_match:
        return int(number_match.group(1))
    return None

def extract_salary(text: str) -> Optional[int]:
    """Extract monthly salary from text"""
    text = text.lower()
    if 'thousand' in text:
        match = re.search(r'(\d+\.?\d*)\s*thousand', text)
        if match:
            return int(float(match.group(1)) * 1000)
    match = re.search(r'[₹rs]\s*(\d+(?:,\d+)*)', text)
    if match:
        return int(match.group(1).replace(',', ''))
    match = re.search(r'\b(\d{5,6})\b', text)
    if match:
        salary = int(match.group(1))
        if 10000 <= salary <= 500000:
            return salary
    return None

def extract_pan(text: str) -> Optional[str]:
    """Extract PAN number from text"""
    match = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b', text.upper())
    return match.group(1) if match else None

def extract_tenure(text: str) -> Optional[int]:
    """Extract loan tenure in months from text"""
    text = text.lower()
    
    # Try to extract months first
    months_match = re.search(r'(\d+)\s*(?:month|months)', text)
    if months_match:
        months = int(months_match.group(1))
        if 12 <= months <= 60:
            return months
        return None
    
    # Try to extract years and convert to months
    years_match = re.search(r'(\d+)\s*(?:year|years)', text)
    if years_match:
        years = int(years_match.group(1))
        months = years * 12
        if 12 <= months <= 60:
            return months
        return None
    
    return None

def validate_pan(pan: str) -> dict:
    """Validate PAN format"""
    if not pan or len(pan) != 10:
        return {"valid": False, "error": f"PAN must be exactly 10 characters (got {len(pan)})", "pan": None}
    pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    if not re.match(pan_pattern, pan):
        return {"valid": False, "error": "Invalid PAN format. Expected: 5 letters, 4 digits, 1 letter", "pan": None}
    return {"valid": True, "error": None, "pan": pan}

# ================= UNIFIED AGENT =================
UNIFIED_PROMPT = """You are Nexus AI, a professional and friendly loan advisor. You handle the entire loan application process in one smooth conversation.

**Your Tools:**
1. **get_market_rates_tool** - Show current interest rates
2. **check_user_history_tool** - Check if customer is returning
3. **verification_agent_tool** - Verify customer KYC (only call ONCE with PAN)
4. **underwriting_agent_tool** - Evaluate loan eligibility
5. **sanction_letter_tool** - Generate approval letter

**Current State:**
- Customer Name: {customer_name}
- Loan Amount: {loan_amount}
- KYC Verified: {kyc_verified}
- Monthly Salary: {monthly_salary}
- Underwriting Status: {underwriting_status}
- Sanction Letter: {sanction_letter}

**CRITICAL: WHEN SALARY IS PROVIDED OR UPLOADED:**
If monthly_salary is shown above (not "Not provided"), you MUST:
1. IMMEDIATELY acknowledge it: "Thank you for uploading your payslip! I can see your monthly salary is {monthly_salary}."
2. Check if user's question was about eligibility/requirements
3. If loan amount is known, tell them if they meet the 2x salary requirement
4. Then ask for PAN to proceed with KYC verification
5. NEVER go blank - ALWAYS respond when salary is present!

**IMPORTANT - SALARY VERIFICATION:**
- If user TYPES salary without uploading a payslip → Ask them to upload the payslip for confirmation
- Example: "I appreciate you sharing your monthly salary. However, to proceed, could you please upload your payslip for verification? This helps us confirm your income."
- Only accept salary as verified when it comes from a payslip upload, not from text input alone

**Example response when salary is uploaded:**
"Thank you for uploading your payslip! I can see your monthly salary is ₹70,000.

Based on your salary:
- For a 24-month loan, your total earnings would be ₹16,80,000
- This means you can apply for loans up to ₹8,40,000 (2x rule met)
✅ You meet the basic requirements!

To proceed with your loan application, I'll need your PAN number for KYC verification. Could you please provide your PAN?"

**Workflow:**

**STAGE 1 - Acknowledge ALL information received:**
- Loan amount mentioned → "Got it, I'll help you with your loan application"
- Salary provided/uploaded → MUST acknowledge with specific amount + eligibility check
- PAN provided → Verify immediately with verification_agent_tool
- NEVER stay silent when user provides information!

**STAGE 2 - Eligibility Check (when loan amount + salary known):**
- Calculate: salary × 24 months vs 2 × loan amount
- Tell user if they meet the requirement
- Explain what they're eligible for

**TENURE VALIDATION (CRITICAL):**
- Valid tenure range: 12-60 months (1-5 years)
- If user says "100 years" or "1 month" → REJECT and ask for valid tenure
- Example: "I see you mentioned 100 years. However, loan tenures must be between 12-60 months (1-5 years). Could you please specify your preferred tenure?"
- Only accept values between 12 and 60 months

**STAGE 3 - KYC Verification:**
- Ask for PAN after acknowledging salary
- Use verification_agent_tool when PAN is provided
- Extract customer name and details

**STAGE 4 - Final Underwriting:**
- Use underwriting_agent_tool with PAN + amount + salary
- If approved → Generate sanction letter
- If rejected → Explain why with alternatives

**CRITICAL RULES:**
- **NEVER GO BLANK** - Always respond to user input!
- **ALWAYS ACKNOWLEDGE SALARY UPLOADS** - Say the exact amount and check eligibility
- When monthly_salary shows a value → You MUST mention it in your response
- Extract loan_amount, salary, PAN from messages and update state
- Be conversational and helpful, not robotic
- If user asks "am I eligible?" check if you have salary + amount, then answer
- Format numbers with commas: ₹2,00,000

**Response Style:**
- Warm and professional
- Always acknowledge what user provided
- Be specific with numbers
- Use ✅ for approval, ❌ for rejection
- Keep responses clear and actionable
"""

# Bind all tools to the LLM
all_tools = [
    get_market_rates_tool,
    check_user_history_tool,
    verification_agent_tool,
    underwriting_agent_tool,
    sanction_letter_tool
]
agent_llm = llm.bind_tools(all_tools)

def agent_node(state: AgentState):
    """Single unified agent that handles everything"""
    logger.info("=== UNIFIED AGENT PROCESSING ===")
    
    # Extract information from latest user message
    last_user_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break
    
    updates = {}
    
    # Check if this is a payslip upload message (force re-extraction of salary)
    is_payslip_upload = "uploaded my payslip" in last_user_msg.lower() or "monthly salary is" in last_user_msg.lower()
    
    # If salary is typed without payslip, ask for payslip confirmation
    is_salary_typed = extract_salary(last_user_msg) is not None and not is_payslip_upload
    
    # Extract loan amount
    if not state.get("loan_amount"):
        amount = extract_loan_amount(last_user_msg)
        if amount:
            updates["loan_amount"] = amount
            logger.info(f"Extracted loan amount: ₹{amount:,}")
    
    # Extract salary ONLY from payslip uploads, not from typed text
    if (not state.get("monthly_salary") or is_payslip_upload) and is_payslip_upload:
        salary = extract_salary(last_user_msg)
        if salary:
            updates["monthly_salary"] = salary
            logger.info(f"Extracted monthly salary: ₹{salary:,}")
    
    # Extract tenure (12-60 months only)
    if not state.get("requested_tenure"):
        tenure = extract_tenure(last_user_msg)
        if tenure:
            updates["requested_tenure"] = f"{tenure} months"
            logger.info(f"Extracted tenure: {tenure} months")
        elif "month" in last_user_msg.lower() or "year" in last_user_msg.lower():
            # User mentioned tenure but it's invalid (too short/long)
            logger.warning(f"Invalid tenure mentioned: {last_user_msg}")
            # Agent will be instructed to reject this
            updates["tenure_invalid"] = True
    
    # Extract PAN
    if not state.get("pan_number"):
        pan = extract_pan(last_user_msg)
        if pan:
            validation = validate_pan(pan)
            if validation["valid"]:
                updates["pan_number"] = validation["pan"]
                logger.info(f"Extracted PAN: {validation['pan']}")
    
    # Build prompt with current state
    loan_amt = updates.get('loan_amount') or state.get('loan_amount')
    salary_amt = updates.get('monthly_salary') or state.get('monthly_salary')
    
    prompt = UNIFIED_PROMPT.format(
        customer_name=state.get("customer_name") or "Not provided",
        loan_amount=f"₹{loan_amt:,}" if loan_amt else "Not specified",
        kyc_verified="Yes ✓" if state.get("kyc_verified") else "No ✗",
        monthly_salary=f"₹{salary_amt:,}" if salary_amt else "Not provided",
        underwriting_status=state.get("underwriting_status", "PENDING"),
        sanction_letter="Generated ✓" if state.get("sanction_letter_url") else "Not generated"
    )
    
    # Add note about salary verification if needed
    salary_note = ""
    if is_salary_typed:
        salary_note = "\n\nIMPORTANT: The user just mentioned their monthly salary in text, but they haven't uploaded a payslip yet. Acknowledge their salary amount and ask them to upload their payslip for verification before proceeding."
    
    # Get response from LLM
    result = agent_llm.invoke([SystemMessage(content=prompt + salary_note)] + state["messages"])
    
    updates["messages"] = [result]
    return updates

def tool_node(state: AgentState):
    """Execute tools and update state"""
    logger.info("=== EXECUTING TOOLS ===")
    last_message = state["messages"][-1]
    
    tool_map = {tool.name: tool for tool in all_tools}
    tool_messages = []
    state_updates = {}
    
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            logger.info(f"Calling tool: {tool_name}")
            
            tool = tool_map.get(tool_name)
            if tool:
                try:
                    result = tool.invoke(tool_args)
                    from langchain_core.messages import ToolMessage
                    tool_messages.append(
                        ToolMessage(content=json.dumps(result, indent=2), tool_call_id=tool_call["id"])
                    )
                    
                    # Update state based on tool results
                    if tool_name == "verification_agent_tool":
                        if result.get("verified"):
                            state_updates["kyc_verified"] = True
                            state_updates["customer_name"] = result.get("name", state.get("customer_name"))
                            state_updates["pan_number"] = result.get("pan")
                            state_updates["phone_number"] = result.get("phone")
                            logger.info(f"KYC VERIFIED: {result.get('name')}")
                    
                    elif tool_name == "underwriting_agent_tool":
                        status = result.get("status")
                        state_updates["underwriting_status"] = status
                        
                        if status == "APPROVED":
                            state_updates["approved_interest_rate"] = result.get("interest_rate")
                            state_updates["credit_score"] = result.get("credit_score")
                            logger.info(f"LOAN APPROVED at {result.get('interest_rate')}%")
                        
                        elif status == "REJECTED":
                            state_updates["credit_score"] = result.get("credit_score")
                            logger.info(f"LOAN REJECTED: {result.get('reason')}")
                        
                        elif status == "NEED_SALARY":
                            logger.info("Need salary information")
                    
                    elif tool_name == "sanction_letter_tool":
                        state_updates["sanction_letter_url"] = result.get("pdf_url")
                        logger.info(f"Sanction letter generated: {result.get('pdf_url')}")
                
                except Exception as e:
                    logger.error(f"Tool error: {e}")
                    from langchain_core.messages import ToolMessage
                    tool_messages.append(
                        ToolMessage(content=f"Error: {str(e)}", tool_call_id=tool_call["id"])
                    )
    
    state_updates["messages"] = tool_messages
    return state_updates

# ================= GRAPH CONSTRUCTION =================
def build_graph():
    """Build the simplified single-agent workflow"""
    memory = MemorySaver()
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    
    # Start with agent
    workflow.add_edge(START, "agent")
    
    # Agent decides: call tools or end
    def route_agent(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END
    
    workflow.add_conditional_edges("agent", route_agent, {"tools": "tools", END: END})
    
    # After tools, always return to agent
    workflow.add_edge("tools", "agent")
    
    return workflow.compile(checkpointer=memory)

# Build the graph
graph = build_graph()

# ================= EXECUTION =================
def run_agent(user_input: str, thread_id: str):
    """Execute the unified agent workflow"""
    logger.info(f"\n{'='*60}")
    logger.info(f"USER INPUT: {user_input}")
    logger.info(f"THREAD ID: {thread_id}")
    logger.info(f"{'='*60}\n")
    
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    
    try:
        events = []
        for event in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
            stream_mode="values"
        ):
            events.append(event)
        
        if events:
            final_state = events[-1]
            logger.info(f"\nFINAL STATE:")
            logger.info(f"Customer: {final_state.get('customer_name')}")
            logger.info(f"Loan Amount: {final_state.get('loan_amount')}")
            logger.info(f"KYC Verified: {final_state.get('kyc_verified')}")
            logger.info(f"Underwriting: {final_state.get('underwriting_status')}")
            logger.info(f"{'='*60}\n")
            
            # Extract final response
            messages = final_state.get("messages", [])
            logger.info(f"Total messages in final state: {len(messages)}")
            
            for i, msg in enumerate(reversed(messages)):
                logger.info(f"Message {i}: Type={type(msg).__name__}, HasContent={hasattr(msg, 'content')}, ContentLength={len(msg.content) if hasattr(msg, 'content') and msg.content else 0}")
                if isinstance(msg, AIMessage) and msg.content:
                    logger.info(f"Returning AIMessage content: {msg.content[:100]}...")
                    return msg.content
            
            logger.warning("No AIMessage with content found - returning default")
            return "I'm processing your request. Please continue."
        
        return "I'm here to help with your loan application. How can I assist you?"
    
    except Exception as e:
        logger.error(f"ERROR in run_agent: {e}")
        import traceback
        traceback.print_exc()
        return f"I apologize, but I encountered an error: {str(e)}. Please try rephrasing your request."
