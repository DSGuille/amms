from dataclasses import dataclass
from typing import Dict, FrozenSet, Union, Optional, List
from abc import ABC, abstractmethod


# Tokens
@dataclass(frozen=True)
class AtomicToken:
    name: str

    def __repr__(self):
        return self.name


@dataclass(frozen=True)
class MintedToken:
    pair: FrozenSet[AtomicToken]

    def __repr__(self):
        t0, t1 = sorted(self.pair, key=lambda t: t.name)
        return f"LP({t0}-{t1})"


Token = Union[AtomicToken, MintedToken]


# Wallet
class Wallet:
    def __init__(self, owner: str):
        self.owner = owner
        self.balances: Dict[Token, float] = {}

    def deposit(self, token: Token, amount: float):
        self.balances[token] = self.balances.get(token, 0.0) + amount

    def withdraw(self, token: Token, amount: float):
        if self.balances.get(token, 0.0) < amount:
            raise ValueError(f"{self.owner} insufficient {token}")
        self.balances[token] -= amount

    def balance(self, token: Token) -> float:
        return self.balances.get(token, 0.0)


# Market Maker Interface
class MarketMaker(ABC):

    @abstractmethod
    def lp_minted(self, reserves, amounts, total_lp):
        pass

    @abstractmethod
    def swap_out(self, reserves, token_in, amount_in):
        pass

    @abstractmethod
    def redeem(self, reserves, lp_amount, total_lp):
        pass

# AMM
class AMM:
    def __init__(self, token0, token1, market_maker: MarketMaker, reserve0=0.0, reserve1=0.0):
        self.tokens = frozenset({token0, token1})
        self.reserves = {token0: reserve0, token1: reserve1}
        self.mm = market_maker
    def deposit(self, amounts):
        for t, a in amounts.items(): self.reserves[t] += a
    def withdraw(self, amounts):
        for t, a in amounts.items(): self.reserves[t] -= a

# -------- Transaction --------
@dataclass
class Transaction:
    type: str
    wallet: Wallet
    token0: Optional[AtomicToken] = None
    token1: Optional[AtomicToken] = None
    amount0: float = 0.0

class State:
    def __init__(self, wallets: List[Wallet], amms: List[AMM]):
        self.wallets = {w.owner: w for w in wallets}
        self.amms = amms
    def find_amm(self, t0, t1):
        return next(a for a in self.amms if a.tokens == frozenset({t0, t1}))
    def swap(self, tx: Transaction):
        amm = self.find_amm(tx.token0, tx.token1)
        out = amm.mm.swap_out(amm.reserves, tx.token0, tx.amount0)
        tx.wallet.withdraw(tx.token0, tx.amount0)
        amm.deposit({tx.token0: tx.amount0})
        amm.withdraw({tx.token1: out})
        tx.wallet.deposit(tx.token1, out)

# Uniswap V1 CPMM
class UniswapV1(MarketMaker):
    """
    CPMM x*y=k
    Always ETH <-> TOKEN
    """

    def lp_minted(self, reserves, amounts, total_lp):
        tokens = list(reserves.keys())
        eth = [t for t in tokens if t.name == "ETH"][0]
        tok = [t for t in tokens if t != eth][0]

        if total_lp == 0:
            # Pool creation
            return (amounts[eth] * amounts[tok]) ** 0.5

        share = amounts[eth] / reserves[eth]
        return share * total_lp

    def swap_out(self, reserves, token_in, amount_in):
        tokens = list(reserves.keys())
        token_out = [t for t in tokens if t != token_in][0]

        x = reserves[token_in]
        y = reserves[token_out]

        k = x * y
        new_x = x + amount_in
        new_y = k / new_x

        return y - new_y

    def redeem(self, reserves, lp_amount, total_lp):
        share = lp_amount / total_lp
        return {t: reserves[t] * share for t in reserves}


# Uniswap V2 CPMM
class UniswapV2(MarketMaker):
    def __init__(self, fee=0.01):
        self.fee = fee

    def lp_minted(self, reserves, amounts, total_lp):
        tokens = list(reserves.keys())
        if total_lp == 0:
            return (amounts[tokens[0]] * amounts[tokens[1]]) ** 0.5
        share = min(amounts[t] / reserves[t] for t in tokens)
        return share * total_lp

    def swap_out(self, reserves, token_in, amount_in):
        token_out = [t for t in reserves.keys() if t != token_in][0]
        x, y = reserves[token_in], reserves[token_out]

        amount_in_with_fee = amount_in * (1 - self.fee)
        return y - (x * y) / (x + amount_in_with_fee)

    def redeem(self, reserves, lp_amount, total_lp):
        share = lp_amount / total_lp
        return {t: reserves[t] * share for t in reserves}

# CSMM
class CSMM(MarketMaker):
    """
    x + y = k
    Constant price, no slippage
    """

    def lp_minted(self, reserves, amounts, total_lp):
        tokens = list(reserves.keys())
        t0, t1 = tokens[0], tokens[1]

        if total_lp == 0:
            return amounts[t0] + amounts[t1]

        share = amounts[t0] / reserves[t0]
        return share * total_lp

    def swap_out(self, reserves, token_in, amount_in):
        tokens = list(reserves.keys())
        token_out = [t for t in tokens if t != token_in][0]

        price = reserves[token_out] / reserves[token_in]
        return amount_in * price

    def redeem(self, reserves, lp_amount, total_lp):
        share = lp_amount / total_lp
        return {t: reserves[t] * share for t in reserves}


# CMMM (Constant Mean) 
class CSMM(MarketMaker):
    def __init__(self, price: float):
        self.price = price  # P fijo del pool

    def lp_minted(self, reserves, amounts, total_lp):
        tokens = list(reserves.keys())
        t0, t1 = tokens[0], tokens[1]

        if total_lp == 0:
            return amounts[t0] + amounts[t1] / self.price

        share = amounts[t0] / reserves[t0]
        return share * total_lp

    def swap_out(self, reserves, token_in, amount_in):
        tokens = list(reserves.keys())
        token_out = [t for t in tokens if t != token_in][0]

        if token_in.name == "ETH":
            # ETH -> DAI
            return amount_in * self.price
        else:
            # DAI -> ETH
            return amount_in / self.price

    def redeem(self, reserves, lp_amount, total_lp):
        share = lp_amount / total_lp
        return {t: reserves[t] * share for t in reserves}


# HFMM (Hybrid Function Market Maker)
class HFMM(MarketMaker):
    def __init__(self, lmbda: float = 0.5, p_init: float = 2500.0):
        self.lmbda = lmbda
        self.p = p_init

    def _calculate_k(self, x, y):
        y_norm = y / self.p
        return self.lmbda * (x + y_norm) / 2 + (1 - self.lmbda) * (x * y_norm)**0.5

    def lp_minted(self, reserves, amounts, total_lp):
        tokens = list(reserves.keys())
        if total_lp == 0:
            return self._calculate_k(amounts[tokens[0]], amounts[tokens[1]])
        k_old = self._calculate_k(reserves[tokens[0]], reserves[tokens[1]])
        k_new = self._calculate_k(reserves[tokens[0]] + amounts[tokens[0]], 
                                  reserves[tokens[1]] + amounts[tokens[1]])
        return ((k_new - k_old) / k_old) * total_lp

    def swap_out(self, reserves, token_in, amount_in):
        tokens = list(reserves.keys())
        is_token_eth = (token_in.name == "ETH")
        x_old, y_old = reserves[tokens[0]], reserves[tokens[1]] # eth, dai
        
        k_target = self._calculate_k(x_old, y_old)
        
        if is_token_eth:
            x_new = x_old + amount_in
            y_new_val = self._solve_for_y(x_new, k_target)
            return max(0, y_old - y_new_val)
        else:
            y_new = y_old + amount_in
            x_new_val = self._solve_for_x(y_new, k_target)
            return max(0, x_old - x_new_val)

    def _solve_for_y(self, x, k):
        y_guess = k * self.p
        for _ in range(20):
            y_n = y_guess / self.p
            f = self.lmbda * (x + y_n) / 2 + (1 - self.lmbda) * (x * y_n)**0.5 - k
            df = self.lmbda / (2 * self.p) + (1 - self.lmbda) * 0.5 * (x / (y_guess * self.p))**0.5
            y_guess -= f / df
            if abs(f) < 1e-8: break
        return y_guess

    def _solve_for_x(self, y, k):
        x_guess = k
        y_n = y / self.p
        for _ in range(20):
            f = self.lmbda * (x_guess + y_n) / 2 + (1 - self.lmbda) * (x_guess * y_n)**0.5 - k
            df = self.lmbda / 2 + (1 - self.lmbda) * 0.5 * (y_n / x_guess)**0.5
            x_guess -= f / df
            if abs(f) < 1e-8: break
        return x_guess

    def redeem(self, reserves, lp_amount, total_lp):
        share = lp_amount / total_lp
        return {t: reserves[t] * share for t in reserves}