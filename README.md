# Team Nexus: AI Conversational Loan Agent (EY Techathon 6.0)

This repository contains the EY Techathon 6.0 (BFSI) project for Team Nexus. It's an AI-driven conversational chatbot designed to automate the end-to-end personal loan origination process for an NBFC. The solution replaces manual sales processes with an intelligent 24/7 agent to increase conversion rates and operational efficiency.

## 1. The Challenge

  * **Problem:** The existing manual process for upselling personal loans is inefficient, costly, and creates operational bottlenecks, slowing growth.
  * **Solution:** A conversational AI built on a **Master-Worker agent architecture**. A central Master Agent orchestrates specialized worker agents to manage the full customer journey:
    1.  Conversation & Intent Capture
    2.  KYC & Document Verification
    3.  Credit Evaluation & Eligibility
    4.  Loan Approval & Offer Generation
    5.  Sanction Letter Generation

## 2. Key Features

  * **Multi-Agent System:** A Master Agent (Orchestrator) manages a stateful conversation and delegates tasks to specialized Worker Agents.
  * **Emotional Intelligence:** The chatbot detects user sentiment and adapts its tone for a more human-like, empathetic interaction.
  * **Explainable AI (XAI):** Provides transparent reasons for loan approvals or rejections to build customer trust.
  * **End-to-End Automation:** The entire pipeline is automated, from the initial chat to the final PDF sanction letter.
  * **RBI-Compliant:** Designed with a secure, tamper-proof audit trail for regulatory compliance.

-----

## 3. System Architecture

This is a distributed system of microservices and AI agents.

### 1\. Backend: Orchestration Service (Master Agent)

The "brain" of the operation, built in **Python + Flask**. This is the *only* endpoint the frontend communicates with.

  * It hosts a **LangGraph (LangChain) state machine** to manage the conversation's state.
  * An **LLM (Gemini)** acts as the **Master Agent**, analyzing the state and user input to decide which tool to call next.
  * The **Worker Agents** are defined as "tools" (Python functions) that the Master Agent can execute.

### 2\. Worker Agents (User Journey Flow)

1.  **`Sales Agent`:** Engages the user to capture loan intent.
2.  **`Verification Agent`:** Asks for KYC, then calls the **Mock CRM Server** to validate user data.
3.  **`Underwriting Agent`:** Calls the **Mock Credit Bureau** for a credit score and the **Mock Offer Mart** for pre-approved limits. Uses LLM reasoning to approve or reject.
4.  **`Sanction Letter Agent`:** Uses **ReportLab** to dynamically generate a PDF sanction letter with the approved loan details.
5.  **`Notification Agent`:** Delivers the final offer and PDF link to the user.

### 3\. Mocked Bank Infrastructure

To simulate a real banking environment, three independent **Flask** microservices are run separately:

  * **Mock CRM Server:** Responds to KYC validation requests.
  * **Mock Credit Bureau:** Provides dummy credit scores.
  * **Mock Offer Mart:** Provides pre-approved loan limits.

-----

## 4. Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | HTML5, CSS3, JavaScript | Simple, responsive web chat interface. |
| **Backend** | Python, Flask, Flask-CORS | Manages the main orchestration service and workflow. |
| **AI Agents** | LangChain (LangGraph), Gemini API | Manages agent state, logic flow, and LLM reasoning. |
| **Database** | MySQL (hosted on Render) | Securely stores user data and approved loan logs. |
| **PDF Generation** | ReportLab | Automatic generation of sanction letters. |
| **Deployment** | Render (for Backend/DB) | Hosting the live application. |

-----

## 5. Live Demo & Deployment

This application is deployed on Render. End-users can access the live chatbot here without needing to run any code.

  * **Live Demo URL:** '[our final url endpoint]'

The "How to Run Locally" section below is intended for developers, testers, or judges who wish to run the project's source code on their own machine.

-----

## 6. How to Run Locally

### 1\. Prerequisites

  * Python 3.10+
  * A Gemini API Key (or other LLM API Key)

### 2\. Run the Backend Services

You must run all four Flask services in separate terminals. The main orchestrator has **CORS enabled**, allowing the `index.html` file to call it.

```bash
# Terminal 1: Run Mock CRM
cd mock-services/crm
pip install -r requirements.txt
flask run --port 5001

# Terminal 2: Run Mock Credit Bureau
cd mock-services/credit-bureau
pip install -r requirements.txt
flask run --port 5002

# Terminal 3: Run Mock Offer Mart
cd mock-services/offer-mart
pip install -r requirements.txt
flask run --port 5003

# Terminal 4: Run the Main Orchestrator
cd orchestration-service
pip install -r requirements.txt
export LLM_API_KEY="your-api-key-here"
flask run --port 5000
```

### 3\. Run the Frontend

No web server is needed.

1.  Navigate to the `frontend` folder in your file explorer.
2.  Double-click the **`index.html`** file to open it directly in your browser.
3.  The JavaScript will automatically connect to the orchestrator running on `http://localhost:5000`.

-----
