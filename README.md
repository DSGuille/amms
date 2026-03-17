# AMM Chaotic Scenarios — Simulation Notebooks

This project explores the structural fragility of Automated Market Makers (AMMs) under chaotic market conditions using a custom AMM simulation environment.

## Structure

- `amm_basics.py` — core AMM framework: tokens, wallets, liquidity pools, swap logic
- `simulation_environment.ipynb` — simulation of a Constant Product Market Maker and a Constant Sum Market Maker with real data
- `chaotic_scenario_1.ipynb` — liquidity death spiral under panic withdrawals
- `chaotic_scenario_2.ipynb` — crash scenario with friction arbitrage and persistent price divergence
- `chaotic_scenario_3.ipynb` — increasing variance stochastic process and its effect on impermanent loss

## Results

Each notebook contains simulation code, theoretical background, and animated visualizations exported as GIFs.
