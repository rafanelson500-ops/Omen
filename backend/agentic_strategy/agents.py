import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from agentic_strategy.tools import place_trade, get_data, read_options_chain, get_order_flow_data, get_regime_data
# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "your-openai-api-key-here":
    raise EnvironmentError(
        "OPENAI_API_KEY is not set.\n"
        "Add it to backend/.env:  OPENAI_API_KEY=sk-..."
    )

# ── LLM ───────────────────────────────────────────────────────────────────────
llm = LLM(model="gpt-5.2", api_key=api_key)

agents = [
    Agent(
        role="Contextualizer",
        goal="You will get historical OHLCV for 5 hours and you will profide important levels, general price history, and most importantly CURRENT PRICE.",
        backstory="You are a contextualizer who uses the provided data to contextualize the reports.",
        llm=llm,
        tools=[get_data],
    ),
    Agent(
        role="Options Analyst",
        goal="Use SPX options data to predict the direction of ES. It should include any relevant levels that you find and how the price could react.",
        backstory="You are all daytraders and need to keep that in mind when placing trades and making reports. You are analyzing mirco market structure. You and expert in options trading. You have a deep understanding of the options market and the SPX options data. You know how dealers position based off of gamma and other information.",
        llm=llm,
        tools=[read_options_chain],
    ),
    Agent(
        role="Regime Analyst",
        goal="Use the Options Analyst's report and any provided features to categorize the volatility and liquidity regime of the market.",
        backstory="You are all daytraders and need to keep that in mind when placing trades and making reports. You are analyzing mirco market structure. You are an analyst who uses the Options Analyst's report and any provided features to categorize the volatility and liquidity regime of the market.",
        llm=llm,
        tools=[get_regime_data],
    ),
    Agent(
        role="Order Flow Analyst",
        goal="Use the Options Analyst's report and the Regime Analyst's report to analyze the order flow of the market. You should look for any imbalanced in volume profile including low volume nodes, high volume nodes, and breakouts.",
        backstory="You are all daytraders and need to keep that in mind when placing trades and making reports. You are analyzing micro market structure. You are a trader who uses the Options Analyst's report and the Regime Analyst's report to make a decision on the microstructure of the market. You include the full narritive and don't forget any tail risk.",
        llm=llm,
        tools=[get_order_flow_data],
    ),
    Agent(
        role="Trade Strategist",
        goal="Use the Options Analyst's report and the Regime Analyst's report and the Order Flow Analyst's report to make a decision on what position to take and what targets to aim for. You should include side, position size, and targets.",
        backstory="You are all daytraders and need to keep that in mind when placing trades and making reports. You are analyzing micro market structure. You are a trader who uses the Options Analyst's report and the Regime Analyst's report and the Order Flow Analyst's report to make a decision on what to trade and how to trade it. You are aggressive and take calculated risks. You set meaningful targets for stop loss and take profit and are not afraid to take a loss if the trade is not working out. You size your positions based on previous reports.",
        llm=llm,
        tools=[place_trade],
    )
]