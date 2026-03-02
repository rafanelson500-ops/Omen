from crewai import Task
from agentic_strategy.agents import agents

contextualizer_task = Task(
    description="You will get historical OHLCV for 10 hours and you will profide important levels, general price history, and most importantly CURRENT PRICE.",
    expected_output="Current price at the top, then a brief summary of the price history and any important levels that you find. Also include the time of day (provided in UTC)",
    agent=agents[0],
)
options_analyst_task = Task(
    description="Use the read_options_chain tool to get the SPX options data and use it to predict the direction of ES. It should include any relevant levels that you find and how the price could react.",
    expected_output="A 1-2 paragraph report with the direction of ES and any relevant levels that you find and how the price could react. Include price ranges or specific levels and state your confidence and what happens when your narritive breaks (exit trade, reverse, etc.)",
    agent=agents[1],
    context=[contextualizer_task],
)

regime_analyst_task = Task(
    description="Use the Options Analyst's report and any provided features to categorize the volatility and liquidity regime of the market. Also use the get_regime_data tool to get VWAP and other relevant features.",
    expected_output="A 1-2 paragraph report with the volatility and liquidity regime of the market. Include the volatility and liquidity regime and state your confidence.",
    agent=agents[2],
    context=[contextualizer_task, options_analyst_task],
)

order_flow_analyst_task = Task(
    description="Use the Options Analyst's report and the Regime Analyst's report to analyze the order flow of the market. You should look for any imbalances in volume profile including low volume nodes, high volume nodes, and breakouts. Take regime into account when suggesting trades. Also use the get_order_flow_data tool to get value area levels and other relevant features.",
    expected_output="A 1-2 paragraph report with the state of orderflow in the market. It should include imbalance levels and state if we are at one. Suggest levels of importance and what they could mean.",
    agent=agents[3],
    context=[contextualizer_task, options_analyst_task, regime_analyst_task],
)

trade_strategist_task = Task(
    description="Use the Options Analyst's report and the Regime Analyst's report and the Order Flow Analyst's report to make a decision on what position to take and what targets to aim for. You should include side, position size, and targets.",
    expected_output="The tool call result with no extra text OR the exact text 'PASS' only if you are not taking a trade",
    agent=agents[4],
    context=[contextualizer_task, options_analyst_task, regime_analyst_task, order_flow_analyst_task],
)

######################

tasks = [
    contextualizer_task,
    options_analyst_task,
    regime_analyst_task,
    order_flow_analyst_task,
    trade_strategist_task,
]