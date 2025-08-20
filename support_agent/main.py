import logging
import click
import uvicorn
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from common.langgraph_agent import create_agent
from common.langgraph_agent_executor import LangGraphAgentExecutor
from langchain_core.tools import tool # Import tool decorator

## langgraph tool functions


load_dotenv()
@tool
def get_knowledge(query: str) -> str:
    """Retrieve knowledge from the support agent."""
    # This function would typically call the support agent's API to get knowledge
    return """Aura watches, such as the Crossbeats Orbit Aura and Cubitt Aura, are fitness and health trackers that offer a range of features, including heart rate monitoring, sleep tracking, and blood oxygen level monitoring. They often come with companion apps, like CB-FitPro for Crossbeats or a similar app for Cubitt, that sync with the watch to display and analyze collected data. These apps also allow for customization, such as changing watch faces and setting reminders. 
Aura Watch Models and Features:
Crossbeats Orbit Aura:
This model features a Super AMOLED screen, Bluetooth 5.3, and a variety of sensors including heart rate, SpO2, and accelerometer. It is compatible with iOS and Android devices and offers over 500 customizable watch faces. 
Cubitt Aura:
This model boasts a premium aluminum design and offers Bluetooth calling, comprehensive health tracking (including stress and heart rate), and over 60 sports modes. It also features an AMOLED display, 10-day battery life, and a waterproof design, according to cubittofficial.com. 
Aura Watch Ecosystem and Data:
Aura App: Acts as the central hub for managing and analyzing data collected by the watch, including health trends and personalized insights.
Cloud Platform: Uses AI to process user data and can alert users and healthcare providers of potential health issues.
Data Syncing: Aura apps often sync with other health platforms like Apple HealthKit. 
Other Aura Devices:
AURA Strap 2:
A device that works with Apple Watches to provide body composition analysis and tracking. 
Aura for criminal and court records:
Offers identity protection services by monitoring public records and alerting users to potential misuse of their information, according to Aura. """

@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=8002)
def main(host, port):

    skill = AgentSkill(
        id="answer_question",
        name="Answer Question",
        description="Answers user questions about Aura devices and services.",
        tags=["support", "aura", "devices"],
        examples=[ "What is the battery life of the Crossbeats Orbit Aura watch?",
                   "How do I reset my Cubitt Aura watch?",
                   "What health metrics does the Aura app track?" ],
    )
    agent_card = AgentCard(
        name="Support Agent",
        description="Handles user support queries and product information for Aura Devices.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
    )

    system_prompt = """You are a support agent who handles support queries and product information for Aura Devices.
        
        """
    
    tools = [get_knowledge]
    agent = create_agent(system_prompt=system_prompt, tools=tools)
   
    agent_executor = LangGraphAgentExecutor(agent, agent_card)
    handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    uvicorn.run(app.build(), host=host, port=port)

if __name__ == "__main__":
    main()
